#!/usr/bin/env python3
"""Stage 4：Jev 當**離線訓練的突破過濾器**，嚴格 OOS 檢定它是否有增益。

協定（違反即無效）：
  - 資料分三段：train 前 50%（唯一用來擬合門檻）→ val 25%（選門檻）→ test 25%（只跑一次）
  - Jev 只在「突破訊號」那根棒被呼叫（不是每根棒）
  - 成本計入（$0.042 / M input token），報告同時給含成本與不含
  - state 只放**該根棒**的市場資料（嚴禁多根 K 棒 —— 前次實測 state 會被污染）
  - 中性、零引導提問（前次 prompt 含答案提示導致 389/389 退化）
  - 快取到 runtime/breakout_jev2/jev_cache.json，同一 key 不重複計費

方法論警告：本階段結果**必須以 Stage 1 為前提解讀**。若 Stage 1 判定無 edge，
Jev 過濾器只能在「負期望值」上做選擇 —— 最好的結果也只是少虧。
"""
import hashlib
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

sys.path.insert(0, "/root/Crypto-Backtesting-Lab")
from research.breakout_jev2.lib_backtest import backtest, load_env, metrics
from research.breakout_jev2.lib_data import add_features, load_5m

load_env()   # 從 .env.local 載入 AI_GATEWAY_API_KEY

GATEWAY = "https://ai-gateway.vercel.sh/v4/ai/evaluation-model"
API_KEY = os.getenv("AI_GATEWAY_API_KEY", "").strip()
if not API_KEY:
    raise SystemExit("AI_GATEWAY_API_KEY 未設定：確認 .env.local 存在且有該行")
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "ai-gateway-protocol-version": "0.0.1",
    "ai-evaluation-model-specification-version": "4",
    "ai-model-id": "typesafe-ai/jev",
}
CACHE = "/root/Crypto-Backtesting-Lab/runtime/breakout_jev2/jev_cache.json"
OUT = "/root/Crypto-Backtesting-Lab/runtime/breakout_jev2"
JEV_HORIZON = 48
LEG = 2.0
LOOKBACK = 576
STOP_ATR, TARGET_ATR, BRK_MAX = 2.0, 4.0, 1.0
TAGS = ["BTC_USDT", "APT_USDT", "SUI_USDT", "FIL_USDT", "BCH_USDT"]
TOKEN_COST_PER_M = 0.042
THRESHOLDS = np.round(np.arange(0.20, 0.801, 0.05), 2)

_cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}


def jev_call(state: dict) -> dict:
    """單根棒問 Jev：這個突破先到 +2ATR 還是 -2ATR。"""
    key = hashlib.md5(json.dumps(state, sort_keys=True).encode()).hexdigest()
    if key in _cache:
        return _cache[key]
    body = json.dumps({"state": state, "questions": {
        "first_touch": {
            "type": "choice",
            "instructions": (f"價格剛突破。接下來 {JEV_HORIZON} 根 5 分鐘 K 線內，"
                             f"哪個價位會先被觸及：繼續同方向走 {LEG} ATR，還是反向走 {LEG} ATR？"),
            "criteria": {"continue_further": f"先同向再走 {LEG} ATR",
                         "reverse_back": f"先反向走 {LEG} ATR"},
        },
        "conf": {
            "type": "score",
            "instructions": "你對這個判斷的把握程度",
            "criteria": ["幾乎沒把握", "略有把握", "中等把握", "很有把握", "極有把握"],
        },
    }}).encode()
    last = None
    for att in range(3):
        try:
            req = urllib.request.Request(GATEWAY, data=body, headers=HEADERS, method="POST")
            with urllib.request.urlopen(req, timeout=60) as r:
                dd = json.loads(r.read())
            A = dd["answers"]
            pr = A["first_touch"]["probabilities"]
            res = {"choice": A["first_touch"]["choice"],
                   "p_cont": float(pr.get("continue_further", 0.0)),
                   "conf": float(A["conf"]["score"]),
                   "tok": int(dd.get("usage", {}).get("inputTokens", 0))}
            _cache[key] = res
            return res
        except Exception as ex:                     # noqa: BLE001
            last = ex
            time.sleep(2 * (att + 1))
    return {"choice": "ERR", "p_cont": None, "conf": None, "tok": 0, "err": str(last)[:120]}


def build_state(df: pd.DataFrame, i: int, asset: str) -> dict:
    """只放該根棒的資料（嚴禁塞多根 K 棒）。"""
    row = df.iloc[i]
    a = float(row["atr"])
    return {
        "asset": asset, "timeframe": "5 minute",
        "current_close": round(float(row["close"]), 2),
        "atr_14": round(a, 4),
        "atr_as_pct_of_price": round(a / float(row["close"]) * 100, 3),
        "recent_1bar_return_pct": None if pd.isna(row["ret_1"]) else round(float(row["ret_1"]), 3),
        "recent_12bar_return_pct": None if pd.isna(row["ret_12"]) else round(float(row["ret_12"]), 2),
        "recent_48bar_return_pct": None if pd.isna(row["ret_48"]) else round(float(row["ret_48"]), 2),
        "price_broke_above_prior_high": True,
        "breakout_distance_in_atr": round((float(row["close"]) - float(row[f"don_hi_{LOOKBACK}"])) / a, 3),
    }


def signal_indices(df: pd.DataFrame, start: int = 0, end: int | None = None) -> list[int]:
    """突破訊號棒（與 backtest 的進場條件一致）。"""
    n = len(df) if end is None else end
    c = df["close"].values
    a = df["atr"].values
    hi = df[f"don_hi_{LOOKBACK}"].values
    out = []
    for i in range(start, n - 1):
        if np.isnan(a[i]) or np.isnan(hi[i]) or a[i] <= 0:
            continue
        if c[i] > hi[i] and (c[i] - hi[i]) / a[i] <= BRK_MAX:
            out.append(i)
    return out


def first_touch(df: pd.DataFrame, i: int) -> str:
    """真值：先碰到 +LEG ATR（cont）還是 -LEG ATR（fail）。"""
    n = len(df)
    if i + 1 >= n or np.isnan(df["atr"].values[i]):
        return "none"
    entry = df["open"].values[i + 1]
    a = df["atr"].values[i]
    if a <= 0 or entry <= 0:
        return "none"
    tgt, inv = entry + LEG * a, entry - LEG * a
    h, l = df["high"].values, df["low"].values
    for j in range(i + 1, min(i + 1 + JEV_HORIZON, n)):
        hit_t, hit_i = h[j] >= tgt, l[j] <= inv
        if hit_t and hit_i:
            return "both"
        if hit_t:
            return "cont"
        if hit_i:
            return "fail"
    return "none"


def evaluate_gate(df: pd.DataFrame, gate_mask: np.ndarray, start: int, end: int) -> dict:
    """在 [start, end) 上用 gate 跑回測（gate 需覆蓋全 df，僅該區間生效）。"""
    tr, eq = backtest(df, LOOKBACK, STOP_ATR, TARGET_ATR, BRK_MAX,
                      start=start, end=end, jev_gate=gate_mask)
    return metrics(tr, eq, end - start)


def main() -> None:
    payload = {}
    total_tok = 0
    for tag in TAGS:
        try:
            df = add_features(load_5m(tag), lookbacks=[LOOKBACK])
        except FileNotFoundError:
            continue
        n = len(df)
        t1, t2 = int(n * 0.50), int(n * 0.75)
        sigs = signal_indices(df)
        if len(sigs) < 40:
            print(f"[skip] {tag} 訊號不足 {len(sigs)}")
            continue
        print(f"\n{'=' * 70}\n{tag}  {n:,} 根  訊號 {len(sigs)} 根  "
              f"train<{t1:,} / val<{t2:,} / test>={t2:,}\n{'=' * 70}", flush=True)

        # ── 呼叫 Jev（只針對訊號棒，平行 6 執行緒）──
        states = [(i, build_state(df, i, tag.replace("_USDT", "/USDT"))) for i in sigs]
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=6) as ex:
            res = list(ex.map(lambda t: jev_call(t[1]), states))
        el = time.perf_counter() - t0
        tok = sum(r.get("tok", 0) for r in res)
        total_tok += tok
        json.dump(_cache, open(CACHE, "w"))
        errs = sum(1 for r in res if r["choice"] == "ERR")
        print(f"  Jev: {len(res)} 筆  {el:.0f}s ({el / len(res) * 1000:.0f} ms/筆)  "
              f"{tok} tokens = ${tok / 1e6 * TOKEN_COST_PER_M:.5f}  錯誤 {errs}", flush=True)

        p_cont = {}
        for (i, _), r in zip(states, res):
            if r["p_cont"] is not None:
                p_cont[i] = r["p_cont"]

        # ── train：用真值找最佳門檻（真值只在此段使用）──
        truth = {i: first_touch(df, i) for i in sigs}
        tr_sigs = [i for i in sigs if i < t1 and truth[i] in ("cont", "fail")]
        jev_acc = None
        base_rate = None
        if len(tr_sigs) >= 20:
            base_rate = float(np.mean([truth[i] == "cont" for i in tr_sigs]))
            jev_acc = float(np.mean([(p_cont[i] >= 0.5) == (truth[i] == "cont") for i in tr_sigs]))
            base = max(base_rate, 1 - base_rate)
            print(f"  train 段: n={len(tr_sigs)}  Jev 準確率 {jev_acc:.1%}  "
                  f"基準線（多數類）{base:.1%}  "
                  f"→ {'有技能' if jev_acc > base + 0.02 else '無技能（未勝過基準）'}")
        else:
            print(f"  train 段樣本不足（{len(tr_sigs)}）")

        # ── val：選門檻（讓 val 段淨報酬最大）──
        best_thr, best_ret = None, -1e9
        for thr in THRESHOLDS:
            gate = np.ones(n, dtype=np.int8)
            for i in sigs:
                if i >= t1 and i < t2 and p_cont.get(i, 1.0) < thr:
                    gate[i] = 0
            m = evaluate_gate(df, gate, t1, t2)
            if m["n"] < 5:
                continue
            if m["avg_pct"] > best_ret:
                best_thr, best_ret = float(thr), m["avg_pct"]
        if best_thr is None:
            print("  val 段樣本不足，跳過")
            continue

        # ── test：只跑一次 ──
        gate = np.ones(n, dtype=np.int8)
        for i in sigs:
            if i >= t2 and p_cont.get(i, 1.0) < best_thr:
                gate[i] = 0
        m_g = evaluate_gate(df, gate, t2, n)
        m_b = evaluate_gate(df, np.ones(n, dtype=np.int8), t2, n)
        gain = m_g["avg_pct"] - m_b["avg_pct"]
        print(f"  val 選定門檻 thr={best_thr:.2f}（val 淨報酬 {best_ret:+.4f}%）")
        print(f"  test 段：無 Jev n={m_b['n']} 平均 {m_b['avg_pct']:+.4f}%  PF {m_b['pf']:.2f}  |  "
              f"有 Jev n={m_g['n']} 平均 {m_g['avg_pct']:+.4f}%  PF {m_g['pf']:.2f}")
        verdict = ("增益 +%.4f%%" % gain) if gain > 0 else ("無增益（%.4f%%）" % gain)
        if m_g["n"] < 50:
            verdict += "  ⚠️ 樣本不足（<50），標記為無法判定"
        print(f"  → Jev {verdict}")
        payload[tag] = {"best_thr": best_thr, "val_ret_pct": best_ret,
                        "train_n": len(tr_sigs), "jev_accuracy": jev_acc,
                        "majority_base_rate": base_rate,
                        "has_skill": bool(jev_acc is not None and base_rate is not None
                                          and jev_acc > max(base_rate, 1 - base_rate) + 0.02),
                        "test_no_jev": m_b, "test_with_jev": m_g, "gain_avg_pct": gain,
                        "n_signals": len(sigs), "tokens": tok}
    json.dump(payload, open(f"{OUT}/s4_jev_gate.json", "w"), indent=2)
    print(f"\n總 token {total_tok:,}  總成本 ${total_tok / 1e6 * TOKEN_COST_PER_M:.4f}")
    print(f"-> {OUT}/s4_jev_gate.json")


if __name__ == "__main__":
    main()
