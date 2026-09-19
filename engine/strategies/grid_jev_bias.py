"""Grid + Jev 方向偏置 — 用 TypeSafe Jev 決定網格庫存方向。

為什麼用 Jev 而不是規則
----------------------
grid_switcher v2 的方向判定是硬門檻:
    SMA50 > SMA200 且 ADX >= 25 且 (pDI - mDI) > 4  -> long 偏置
在 1692 根有效日線上只觸發 19 次 (1.1%)。門檻寫死 = 幾乎不開火,
而方向偏置實測能改善 MaxDD (-294 -> -182)。

規則做不到的事:
  1. 多因子同時接近門檻時的取捨 (ADX 24.5 到底算不算趨勢?)
  2. 給出「把握程度」 -> 可以漸進調整, 而不是二元開關
  3. 在沒有單一因子過門檻時, 仍能綜合判斷方向

Jev 的優勢正是這三點: 它吃結構化 state、回機率與信心, 不生成文字。

設計
----
1. gate (沿用已驗證規則): nATR >= expanding 歷史中位數才開網格, 否則 flat。
2. 方向 (Jev): 每次再平衡問 Jev「未來 14 天更可能上漲或下跌」, 回 p_up/p_down + 信心。
   - p_up > P_BIAS -> regime = +1 (庫存只准 [0, cap], 跌買)
   - p_down > P_BIAS -> regime = -1 (庫存只准 [-cap, 0], 漲賣)
   - 否則 regime = 0 (中性雙邊)
3. 信心 < CONF_MIN 時一律中性 (不讓低信心的判斷改變風控)。

Jev 呼叫約束 (實測, 勿違反)
---------------------------
- 同請求內所有問題**共用同一 state** -> 一根 K 棒 = 一次請求, 不可批次混合。
- 本策略只在**再平衡點**呼叫 (預設每 7 天), 400 天約 57 次 -> 成本與延遲都可接受。
- 模型版本在 Vercel AI Gateway 無法 pin -> 回測結果會隨模型更新漂移。

輸出: runtime/grid_jev_status.json
可重跑: python engine/strategies/grid_jev_bias.py
"""

from __future__ import annotations

import os
import json
import time
import datetime as dt
import urllib.request
from dataclasses import dataclass

import numpy as np
import pandas as pd

_CANDIDATE_ROOTS = [
    "/app",
    "/root/Crypto-Backtesting-Lab",
    os.getenv("PROJECT_ROOT") or "",
]
ROOT = next(
    (r for r in _CANDIDATE_ROOTS
     if r and os.path.exists(os.path.join(r, "engine", "strategies"))),
    _CANDIDATE_ROOTS[0],
)
RUNTIME_DIR = os.path.join(ROOT, "runtime")
STATUS_PATH = os.path.join(RUNTIME_DIR, "grid_jev_status.json")
CACHE_PATH = os.path.join(RUNTIME_DIR, "grid_jev_cache.json")

# ── 參數 ────────────────────────────────────────────────────────────────
NATR_Q = 0.50          # 波動門檻分位 (expanding), 沿用已驗證值
MIN_HIST = 250         # 門檻至少需要幾天歷史
HR_MULT = 16.0         # half_range = 日線 ATR x 此值
N_GRIDS = 80
P_BIAS = 0.55          # 方向機率超過此值才施加偏置
CONF_MIN = 2.0         # Jev 信心 (0-4) 低於此值 -> 一律中性
JEV_HORIZON_DAYS = 14  # Jev 判斷的時間視野
REBALANCE_DAYS = 7     # 方向再平衡間隔

GATEWAY = "https://ai-gateway.vercel.sh/v4/ai/evaluation-model"


# ── Jev 呼叫 ────────────────────────────────────────────────────────────
def jev_direction(state: dict, api_key: str, timeout: int = 90) -> dict:
    """問 Jev 未來方向。回 {p_up, p_down, confidence, regime, raw}。"""
    body = json.dumps({
        "state": state,
        "questions": {
            "direction": {
                "type": "choice",
                "instructions": f"未來 {JEV_HORIZON_DAYS} 天，這個標的的價格更可能相對現在上漲還是下跌？",
                "criteria": {
                    "up": "淨上漲",
                    "down": "淨下跌",
                },
            },
            "conf": {
                "type": "score",
                "instructions": "你對上述方向判斷的把握程度",
                "criteria": ["幾乎沒把握", "略有把握", "中等把握", "很有把握", "極有把握"],
            },
        },
    }).encode()

    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                GATEWAY, data=body, method="POST",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "ai-gateway-protocol-version": "0.0.1",
                    "ai-evaluation-model-specification-version": "4",
                    "ai-model-id": "typesafe-ai/jev",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read())
            ans = d["answers"]
            probs = ans["direction"]["probabilities"]
            p_up = float(probs.get("up", 0.0))
            p_down = float(probs.get("down", 0.0))
            conf = float(ans["conf"]["score"])
            if conf < CONF_MIN:
                regime = 0
            elif p_up > P_BIAS:
                regime = 1
            elif p_down > P_BIAS:
                regime = -1
            else:
                regime = 0
            return {"p_up": round(p_up, 4), "p_down": round(p_down, 4),
                    "confidence": round(conf, 3), "regime": regime,
                    "tokens": d.get("usage", {}).get("inputTokens", 0)}
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1))
    return {"p_up": None, "p_down": None, "confidence": None,
            "regime": 0, "tokens": 0, "error": str(last)[:120]}


def _cache_load() -> dict:
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH) as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _cache_save(c: dict) -> None:
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(c, f)


def jev_direction_cached(key: str, state: dict, api_key: str) -> dict:
    """帶快取的 Jev 呼叫 — 回測可重跑而不重複計費。"""
    c = _cache_load()
    if key in c:
        return c[key]
    res = jev_direction(state, api_key)
    if res.get("p_up") is not None:
        c[key] = res
        _cache_save(c)
    return res


# ── 指標 (與 grid_switcher 一致, 用同一套) ──────────────────────────────
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("date").reset_index(drop=True)
    hi, lo, cl = df["high"], df["low"], df["close"]
    tr = pd.concat([(hi - lo), (hi - cl.shift()).abs(), (lo - cl.shift()).abs()],
                   axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    df["atr"] = atr
    df["natr"] = atr / cl

    up_move = hi.diff()
    down_move = lo.diff().mul(-1)
    plus_dm = up_move.clip(lower=0).where(up_move > down_move, 0.0)
    minus_dm = down_move.clip(lower=0).where(down_move > up_move, 0.0)
    plus_di = 100 * plus_dm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9)
    df["adx"] = dx.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    df["plus_di"] = plus_di
    df["minus_di"] = minus_di
    df["natr_thr"] = df["natr"].expanding(MIN_HIST).quantile(NATR_Q).shift(1)
    df["sma50"] = cl.rolling(50).mean()
    df["sma200"] = cl.rolling(200).mean()

    # Jev 用的近期報酬 (只含當下之前的資料)
    for k in (5, 14, 30):
        df[f"ret_{k}d"] = cl.pct_change(k) * 100
    return df


# ── 訊號 ────────────────────────────────────────────────────────────────
@dataclass
class JevSignal:
    gate_open: bool
    regime: int
    confidence: float
    p_up: float | None
    p_down: float | None
    reason: str
    indicators: dict


def decide(df: pd.DataFrame, i: int, api_key: str | None = None,
           cached_only: bool = False) -> JevSignal:
    """單根 bar 的判定。gate 用規則, 方向用 Jev。"""
    r = df.iloc[i]
    natr = float(r["natr"])
    thr = r["natr_thr"]
    ind = {
        "natr": f"{natr:.4f}",
        "natr_thr": None if pd.isna(thr) else f"{float(thr):.4f}",
        "adx": round(float(r["adx"]), 1),
        "plus_di": round(float(r["plus_di"]), 1),
        "minus_di": round(float(r["minus_di"]), 1),
        "atr": round(float(r["atr"]), 1),
    }

    if pd.isna(thr):
        return JevSignal(False, 0, 0.0, None, None,
                         f"歷史不足 {MIN_HIST} 天，波動門檻未生效 → flat", ind)

    if natr < float(thr):
        return JevSignal(False, 0, 0.0, None, None,
                         f"nATR {natr:.4f} < 歷史中位 {float(thr):.4f} → flat", ind)

    state = {
        "asset": "BTC/USDT",
        "timeframe": "daily",
        "close": round(float(r["close"]), 1),
        "atr_14d": round(float(r["atr"]), 1),
        "natr": round(natr, 4),
        "natr_historical_median": round(float(thr), 4),
        "adx": round(float(r["adx"]), 1),
        "plus_di": round(float(r["plus_di"]), 1),
        "minus_di": round(float(r["minus_di"]), 1),
        "sma50": round(float(r["sma50"]), 1) if not pd.isna(r["sma50"]) else None,
        "sma200": round(float(r["sma200"]), 1) if not pd.isna(r["sma200"]) else None,
        "return_5d_pct": round(float(r["ret_5d"]), 2) if not pd.isna(r["ret_5d"]) else None,
        "return_14d_pct": round(float(r["ret_14d"]), 2) if not pd.isna(r["ret_14d"]) else None,
        "return_30d_pct": round(float(r["ret_30d"]), 2) if not pd.isna(r["ret_30d"]) else None,
    }

    if api_key is None:
        return JevSignal(True, 0, 0.0, None, None,
                         f"nATR {natr:.4f} >= 門檻 {float(thr):.4f} → 開網格（中性）", ind)

    key = f"{r['date'].date()}_{state['close']}_{state['natr']}"
    res = jev_direction_cached(key, state, api_key) if cached_only is False \
        else _cache_load().get(key, {"regime": 0, "p_up": None, "p_down": None,
                                     "confidence": None})

    reg = res.get("regime", 0)
    label = {1: "long 偏置（庫存只准為正，跌買）",
             -1: "short 偏置（庫存只准為負，漲賣）",
             0: "中性雙邊"}[reg]
    reason = (f"nATR {natr:.4f} >= 門檻 {float(thr):.4f} → 開網格；"
              f"Jev 方向 {label}"
              f"（p_up {res.get('p_up')}, p_down {res.get('p_down')}, "
              f"信心 {res.get('confidence')}/4）")
    return JevSignal(True, reg, res.get("confidence") or 0.0,
                     res.get("p_up"), res.get("p_down"), reason, ind)


# ── 輸出 ────────────────────────────────────────────────────────────────
def write_status(sig: JevSignal, close: float, bar_date) -> dict:
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    side_map = {1: "long", -1: "short", 0: "flat"}
    status = {
        "available": True,
        "running": True,
        "strategy": "grid_jev_bias",
        "version": 1,
        "symbol": "BTC/USDT",
        "grid_mode": side_map[sig.regime] if sig.gate_open else "flat",
        "gate_open": sig.gate_open,
        "regime": sig.regime,
        "confidence": sig.confidence,
        "p_up": sig.p_up,
        "p_down": sig.p_down,
        "reason": sig.reason,
        "indicators": sig.indicators,
        "last_close": round(float(close), 2),
        "bar_date": str(pd.Timestamp(bar_date).date()),
        "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    with open(STATUS_PATH, "w") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)
    return status


def main():
    api_key = os.getenv("AI_GATEWAY_API_KEY")
    from engine.strategies.grid_switcher import load_data
    df = compute_indicators(load_data())
    i = len(df) - 1
    while i > 0 and pd.isna(df["adx"].iloc[i]):
        i -= 1
    sig = decide(df, i, api_key)
    st = write_status(sig, float(df["close"].iloc[i]), df["date"].iloc[i])
    print(f"[{st['updated_at']}] {st['bar_date']} 收盤 {st['last_close']}")
    print(f"gate: {'開' if sig.gate_open else '關'} | regime: {sig.regime}")
    print(f"理由: {sig.reason}")


if __name__ == "__main__":
    main()
