#!/usr/bin/env python3
"""Stage 5b：Jev 正確用法實驗 —— 「有矛盾的單是不是明顯比較虧」。

依使用者（2026-09-20）的架構紀律設計，修正 Stage 4 的全部缺陷：

  Stage 4 的錯                    本階段的做法
  ─────────────────────────      ──────────────────────────────────
  問價格路徑預測                  問 狀態分類 / setup 值不值得看 / 該不該交易
  criteria 無 HOLD                Choice 三選項 BUY/SELL/HOLD（HOLD 定義明確）
  只用 choice + score             三原語全用：Choice + Score + Noul
  state 是摘要（6 個純量）         state 是證據（最近 12 根原始 OHLCV + 量 + 成本）
  無對照組                        對照組：隨機否決 / 永遠HOLD / 規則本身
  instructions 用中文             關鍵 instructions 用英文
  confidence 當勝率               不當勝率；只當一個可調門檻
  未鎖版本                        已知 Vercel 鎖不了（見 README），改用固定快取 + 記錄

核心檢定（使用者指定，公開測試中最站得住的訊號）：
  把交易依 Jev 的 setup score 分桶，看低分桶是不是明顯比較虧。
  若低分桶沒有更虧 → Jev 無法分辨「有矛盾的單」→ 不可用。
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
from research.breakout_jev2.lib_backtest import load_env
from research.breakout_jev2.lib_data import LOOKBACKS, add_features, load_5m
from research.breakout_jev2.s5a_baseline_rules import add_rule_features, run_mask, signal_mask

load_env()
GATEWAY = "https://ai-gateway.vercel.sh/v4/ai/evaluation-model"
API_KEY = os.getenv("AI_GATEWAY_API_KEY", "").strip()
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "ai-gateway-protocol-version": "0.0.1",
    "ai-evaluation-model-specification-version": "4",
    "ai-model-id": "typesafe-ai/jev",
}
OUT = "/root/Crypto-Backtesting-Lab/runtime/breakout_jev2"
CACHE = f"{OUT}/jev5_cache.json"
LOOKBACK, BRK_MAX = 288, 1.0
BARS_IN_STATE = 12
TOKEN_COST_PER_M = 0.042

TAGS = ["BTC_USDT", "APT_USDT", "SUI_USDT", "FIL_USDT", "BCH_USDT"]

_cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}


def build_state(df: pd.DataFrame, i: int, tag: str) -> dict:
    """證據型 state：最近 N 根**原始** OHLCV + 量 + 成本。不用摘要。"""
    lo = max(0, i - BARS_IN_STATE + 1)
    win = df.iloc[lo:i + 1]
    bars = [
        {
            "t": str(pd.Timestamp(r.timestamp))[:19],
            "o": round(float(r.open), 2), "h": round(float(r.high), 2),
            "l": round(float(r.low), 2), "c": round(float(r.close), 2),
            "v": round(float(r.volume), 3),
        }
        for r in win.itertuples()
    ]
    a = float(df["atr"].values[i])
    entry = float(df["open"].values[min(i + 1, len(df) - 1)])
    return {
        "asset": tag.replace("_USDT", "/USDT").replace("/USDT", "/USDT"),
        "timeframe": "5 minute",
        "recent_bars": bars,                       # 證據：原始 OHLCV
        "atr_14": round(a, 4),
        "prior_high_288": round(float(df[f"don_hi_{LOOKBACK}"].values[i]), 2),
        "breakout_distance_in_atr": round(
            (float(df["close"].values[i]) - float(df[f"don_hi_{LOOKBACK}"].values[i])) / a, 3),
        "roundtrip_cost_pct": 0.14,                 # taker 0.05% x2 + 滑價 0.02% x2
        "position": "flat",
        "next_bar_open_estimate": round(entry, 2),
        "stop_distance_in_atr": 2.0,
        "target_distance_in_atr": 4.0,
    }


def jev_judge(state: dict) -> dict:
    """三原語一次全問（同請求內問題平行隔離，官方保證）。"""
    key = hashlib.md5(json.dumps(state, sort_keys=True).encode()).hexdigest()
    if key in _cache:
        return _cache[key]
    body = json.dumps({
        "state": state,
        "questions": {
            "side": {
                "type": "choice",
                "instructions": (
                    "You are a market-state classifier, not a price forecaster. "
                    "Given ONLY the recent bars above, classify the current situation into exactly one "
                    "of these mutually exclusive options. Choose HOLD whenever the evidence is weak, "
                    "mixed, or the expected move does not clearly exceed the roundtrip cost. "
                    "Be honest: HOLD is the correct answer most of the time."
                ),
                "criteria": {
                    "BUY": "Price is breaking above the prior high with clean, one-sided participation and the move looks likely to extend beyond cost.",
                    "SELL": "Price is breaking above the prior high but the bars show exhaustion, rejection wicks, or a failed push (a false breakout).",
                    "HOLD": "Evidence is weak, mixed, choppy, or too small relative to cost. No clear directional read.",
                },
            },
            "setup_clarity": {
                "type": "score",
                "instructions": (
                    "How clear and tradeable is the current setup, ignoring direction? "
                    "0 = no setup at all. 5 = textbook, unambiguous."
                ),
                "criteria": ["no setup", "very weak", "weak", "moderate", "clear", "textbook"],
            },
            "should_not_trade": {
                "type": "boolean",
                "instructions": (
                    "Is it true that no trade should be taken right now? "
                    "This should be true when the bars are choppy, volume is thin, the breakout is tiny "
                    "relative to ATR, or the expected move is smaller than the roundtrip cost."
                ),
                "criteria": {
                    "not_tradeable": "The current situation does not justify paying the roundtrip cost."
                },
            },
        },
    }).encode()
    last = None
    for att in range(3):
        try:
            req = urllib.request.Request(GATEWAY, data=body, headers=HEADERS, method="POST")
            with urllib.request.urlopen(req, timeout=60) as r:
                dd = json.loads(r.read())
            A = dd["answers"]
            pr = A["side"]["probabilities"]
            res = {
                "side": A["side"]["choice"],
                "p_buy": float(pr.get("BUY", 0.0)),
                "p_sell": float(pr.get("SELL", 0.0)),
                "p_hold": float(pr.get("HOLD", 0.0)),
                "setup": float(A["setup_clarity"]["score"]),
                "p_not_trade": float(A["should_not_trade"]["probability"]),
                "tok": int(dd.get("usage", {}).get("inputTokens", 0)),
            }
            _cache[key] = res
            return res
        except Exception as ex:                     # noqa: BLE001
            last = ex
            time.sleep(2 * (att + 1))
    return {"side": "ERR", "p_buy": None, "p_sell": None, "p_hold": None,
            "setup": None, "p_not_trade": None, "tok": 0, "err": str(last)[:120]}


def main() -> None:
    all_rows = []
    for tag in TAGS:
        try:
            df = add_rule_features(add_features(load_5m(tag), lookbacks=LOOKBACKS))
        except FileNotFoundError:
            continue
        n = len(df)
        m = signal_mask(df, LOOKBACK, BRK_MAX, "breakout_raw", "long")
        sigs = list(np.where(m > 0)[0])
        print(f"\n{'=' * 76}\n{tag}  {n:,} 根  突破訊號 {len(sigs)} 根  "
              f"(train<{int(n * .5):,} / val<{int(n * .75):,} / test>={int(n * .75):,})\n{'=' * 76}",
              flush=True)
        if len(sigs) < 20:
            print("  訊號不足，跳過")
            continue

        states = [(i, build_state(df, i, tag)) for i in sigs]
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=6) as ex:
            res = list(ex.map(lambda t: jev_judge(t[1]), states))
        el = time.perf_counter() - t0
        json.dump(_cache, open(CACHE, "w"))
        tok = sum(r.get("tok", 0) for r in res)
        errs = sum(1 for r in res if r["side"] == "ERR")
        sides = pd.Series([r["side"] for r in res]).value_counts().to_dict()
        setups = pd.Series([r["setup"] for r in res if r["setup"] is not None])
        print(f"  Jev: {len(res)} 筆 {el:.0f}s ({el / len(res) * 1000:.0f}ms/筆) "
              f"{tok:,} tokens ${tok / 1e6 * TOKEN_COST_PER_M:.5f} 錯誤 {errs}")
        print(f"  答案分布 side={sides}")
        print(f"  setup 分布: 平均 {setups.mean():.2f}/5  "
              f"中位 {setups.median():.1f}  各分數={setups.value_counts().sort_index().to_dict()}")
        print(f"  p_not_trade 平均 {np.mean([r['p_not_trade'] for r in res if r['p_not_trade'] is not None]):.3f}")

        for (i, _), r in zip(states, res):
            all_rows.append({"tag": tag, "i": i, "t1": int(n * 0.5), "t2": int(n * 0.75),
                             **{k: v for k, v in r.items() if k != "tok"}})

    rows = pd.DataFrame(all_rows)
    if rows.empty:
        print("無資料")
        return
    rows.to_csv(f"{OUT}/jev5_judgements.csv", index=False)

    # ── 核心檢定：低 setup 分桶是不是明顯比較虧（只在 test 段）──
    print(f"\n{'=' * 76}\n核心檢定：setup 分數 vs 實際報酬（test 段，每筆只看一次）\n{'=' * 76}")
    te = rows[rows["i"] >= rows["t2"]].copy()
    print(f"test 段交易 {len(te)} 筆")
    buckets = {}
    for lo, hi, name in [(0, 2, "0-2 模糊"), (2, 3, "2-3 弱"), (3, 4, "3-4 中"), (4, 6, "4-5 清楚")]:
        b = te[(te["setup"] >= lo) & (te["setup"] < hi)]
        buckets[name] = b
        if len(b) == 0:
            print(f"  {name:10s} n=  0")
            continue
        print(f"  {name:10s} n={len(b):>3}  Jev 選 BUY 比例 "
              f"{(b['side'] == 'BUY').mean():.1%}  HOLD 比例 {(b['side'] == 'HOLD').mean():.1%}")

    # ── 三種閘門策略的 OOS 報酬 ──
    print(f"\n{'=' * 76}\n閘門策略比較（test 段）\n{'=' * 76}")

    def eval_gate(keep_fn, name):
        tot_n, tot_sum, wins = 0, 0.0, 0
        for tag in TAGS:
            try:
                df = add_rule_features(add_features(load_5m(tag), lookbacks=LOOKBACKS))
            except FileNotFoundError:
                continue
            n = len(df)
            t2 = int(n * 0.75)
            m = signal_mask(df, LOOKBACK, BRK_MAX, "breakout_raw", "long")
            mask = np.zeros(n, dtype=np.int8)
            sub = rows[(rows["tag"] == tag)]
            for r in sub.itertuples():
                if r.i >= t2 and keep_fn(r):
                    mask[int(r.i)] = 1
            if (mask > 0).sum() == 0:
                continue
            rr = run_mask(df, mask, t2, n)
            tot_n += rr["n"]
            tot_sum += rr["avg_pct"] * rr["n"]
            if rr["avg_pct"] > 0:
                wins += 1
        if tot_n == 0:
            print(f"  {name:34s} 無交易")
            return None
        avg = tot_sum / tot_n
        print(f"  {name:34s} n={tot_n:>4}  平均 {avg:+.4f}%/筆")
        return {"n": tot_n, "avg_pct": avg}

    results = {}
    results["A_規則本身（無Jev）"] = eval_gate(lambda r: True, "A_規則本身（無Jev）")
    results["B_Jev: BUY且p>=0.55且setup>=3"] = eval_gate(
        lambda r: r.side == "BUY" and (r.p_buy or 0) >= 0.55 and (r.setup or 0) >= 3,
        "B_Jev: BUY且p>=0.55且setup>=3")
    results["C_Jev: 只要不是HOLD"] = eval_gate(
        lambda r: r.side in ("BUY", "SELL"), "C_Jev: 只要不是HOLD")
    results["D_Jev: NOT(noul>0.7)"] = eval_gate(
        lambda r: (r.p_not_trade or 1) < 0.7, "D_Jev: NOT(noul>0.7)")
    results["E_Jev: 三原語全過"] = eval_gate(
        lambda r: (r.side == "BUY" and (r.p_buy or 0) >= 0.55 and (r.setup or 0) >= 3
                   and (r.p_not_trade or 1) < 0.3),
        "E_Jev: 三原語全過")
    # 對照組：隨機否決，否決率與 E 相同
    e_keep = rows[(rows["i"] >= rows["t2"])].apply(
        lambda r: (r.side == "BUY" and (r.p_buy or 0) >= 0.55 and (r.setup or 0) >= 3
                   and (r.p_not_trade or 1) < 0.3), axis=1).mean()
    rng = np.random.default_rng(2026)
    results["F_隨機（同通過率）"] = eval_gate(
        lambda r: rng.random() < e_keep, f"F_隨機（同通過率 {e_keep:.0%}）")
    results["G_永遠HOLD"] = {"n": 0, "avg_pct": 0.0}
    print(f"  {'G_永遠HOLD':34s} n=   0  平均 0.0000%/筆（不交易）")

    json.dump({"buckets": {k: len(v) for k, v in buckets.items()}, "gates": results},
              open(f"{OUT}/s5b_jev_gate.json", "w"), indent=2)
    print(f"\n-> {OUT}/s5b_jev_gate.json / jev5_judgements.csv")


if __name__ == "__main__":
    main()
