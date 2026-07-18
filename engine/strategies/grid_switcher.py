"""Grid Switcher Engine — 日線級別趨勢狀態判定，輸出合約網格切換信號。

依據 research/ 三份報告結論:
  - 單一指標方向預測接近隨機 (BTC 日線 N=5)
  - 但「盤整識別」有價值 (B: BBW 精確率 77%)
  - 「突破觸發」有價值 (C: Donchian+SMA 方向 52-56%)

設計哲學 (合約網格場景):
  不預測漲跌, 只識別「當前市場結構」→ 選對應網格類型
  - range : 盤整網格 (區間內低買高賣)  ← B 盤整信號
  - long  : 看多網格 (只做多網格)      ← C 突破上 + SMA多排列
  - short : 看空網格 (只做空網格)      ← C 突破下 + SMA空排列
  - flat  : 不開新網格 / 維持現狀      ← 模糊地帶, 寧可不動

輸出: runtime/strategy_status.json (符合 STRATEGY_STATUS_SCHEMA.md, 擴充 grid_mode)
可重跑: python engine/strategies/grid_switcher.py
"""

from __future__ import annotations

import os
import json
import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd

try:
    import ccxt
except ImportError:
    ccxt = None
try:
    import yfinance as yf
except ImportError:
    yf = None

ROOT = os.getenv("PROJECT_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_CACHE = os.path.join(ROOT, "research", "btc_usdt_1d.csv")
RUNTIME_DIR = os.path.join(ROOT, "runtime")
STATUS_PATH = os.path.join(RUNTIME_DIR, "strategy_status.json")
SYMBOL = "BTC/USDT"


# ── 數據 ────────────────────────────────────────────────────────────────
def load_data() -> pd.DataFrame:
    if os.path.exists(DATA_CACHE):
        df = pd.read_csv(DATA_CACHE)
        if "timestamp" in df.columns:
            df = df.rename(columns={"timestamp": "date"})
        df["date"] = pd.to_datetime(df["date"])
        if len(df) > 200:
            return df
    if ccxt:
        ex = ccxt.binance()
        since = ex.parse8601("2023-01-01T00:00:00Z")
        bars = ex.fetch_ohlcv(SYMBOL, "1d", since=since, limit=1500)
        df = pd.DataFrame(bars, columns=["date", "open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df["date"], unit="ms")
    elif yf:
        df = yf.download("BTC-USD", start="2023-01-01", interval="1d").reset_index()
        df = df.rename(columns={"Open": "open", "High": "high", "Low": "low",
                                "Close": "close", "Volume": "volume"})
    df.to_csv(DATA_CACHE, index=False)
    return df


# ── 指標 ────────────────────────────────────────────────────────────────
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    hi, lo, cl = df["high"], df["low"], df["close"]
    up_move = hi.diff()
    down_move = lo.diff().mul(-1)
    plus_dm = up_move.clip(lower=0).where(up_move > down_move, 0.0)
    minus_dm = down_move.clip(lower=0).where(down_move > up_move, 0.0)
    tr = pd.concat([(hi - lo), (hi - cl.shift()).abs(), (lo - cl.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1/14, adjust=False, min_periods=14).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1/14, adjust=False, min_periods=14).mean() / atr
    di_sum = (plus_di + minus_di).replace(0, 1e-9)
    dx = 100 * (plus_di - minus_di).abs() / di_sum
    adx = dx.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    df["adx"] = adx; df["plus_di"] = plus_di; df["minus_di"] = minus_di; df["atr"] = atr

    ma20 = cl.rolling(20).mean()
    sd20 = cl.rolling(20).std()
    upper = ma20 + 2 * sd20; lower = ma20 - 2 * sd20
    bbw = (upper - lower) / ma20
    df["bbw_pct"] = bbw.rolling(60).apply(lambda x: (x[-1] <= x).mean() * 100, raw=True)
    df["atr_pct"] = (atr / cl) * 100

    df["dc_hi"] = cl.shift(1).rolling(20).max()
    df["dc_lo"] = cl.shift(1).rolling(20).min()
    df["sma50"] = cl.rolling(50).mean()
    df["sma200"] = cl.rolling(200).mean()
    return df


# ── 3 態判定 ────────────────────────────────────────────────────────────
@dataclass
class GridSignal:
    mode: str          # range | long | short | flat
    confidence: float  # 0-1
    reason: str
    indicators: dict


def decide(df: pd.DataFrame, i: int,
           adx_flat: float = 20.0, adx_trend: float = 25.0, di_diff: float = 4.0,
           bbw_pct_th: float = 35.0, atr_pct_th: float = 2.5) -> GridSignal:
    adx = df["adx"].iloc[i]; pdi = df["plus_di"].iloc[i]; mdi = df["minus_di"].iloc[i]
    bp = df["bbw_pct"].iloc[i]; ap = df["atr_pct"].iloc[i]
    cl = df["close"].iloc[i]; dc_hi = df["dc_hi"].iloc[i]; dc_lo = df["dc_lo"].iloc[i]
    sma50 = df["sma50"].iloc[i]; sma200 = df["sma200"].iloc[i]

    # 盤整優先 (B 主力): BBW 收斂 + ATR 低 → range grid
    if bp < bbw_pct_th and ap < atr_pct_th:
        return GridSignal("range", 0.77,
                          f"BBW百分位{bp:.0f}<{bbw_pct_th} & ATR%{ap:.2f}<{atr_pct_th} → 盤整",
                          {"adx": round(adx, 1), "bbw_pct": round(bp, 1), "atr_pct": round(ap, 2)})

    # 趨勢突破 (C 觸發 + A 確認): Donchian 突破 + SMA 排列 + ADX 趨勢
    if cl > dc_hi and sma50 > sma200 and adx >= adx_trend and (pdi - mdi) > di_diff:
        return GridSignal("long", 0.56,
                          f"突破Donchian上軌 + SMA多排列 + ADX{adx:.0f}>= {adx_trend} +DI>-DI",
                          {"adx": round(adx, 1), "pdi": round(pdi, 1), "mdi": round(mdi, 1)})
    if cl < dc_lo and sma50 < sma200 and adx >= adx_trend and (mdi - pdi) > di_diff:
        return GridSignal("short", 0.56,
                          f"跌破Donchian下軌 + SMA空排列 + ADX{adx:.0f}>= {adx_trend} -DI>+DI",
                          {"adx": round(adx, 1), "pdi": round(pdi, 1), "mdi": round(mdi, 1)})

    # 模糊地帶: 不動 (flat)
    return GridSignal("flat", 0.0,
                      f"模糊地帶 ADX{float(adx):.0f} DI差{float(pdi-mdi):+.1f} → 維持現狀",
                      {"adx": round(float(adx), 1), "pdi": round(float(pdi), 1), "mdi": round(float(mdi), 1)})


# ── 輸出 ────────────────────────────────────────────────────────────────
def write_status(sig: GridSignal, close: float, df: pd.DataFrame):
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    side_map = {"range": "flat", "long": "long", "short": "short", "flat": "flat"}
    status = {
        "available": True,
        "running": True,
        "strategy": "grid_switcher",
        "symbol": SYMBOL,
        "exchange": "bingx",
        "grid_mode": sig.mode,           # range / long / short / flat
        "confidence": sig.confidence,
        "reason": sig.reason,
        "indicators": sig.indicators,
        "last_close": round(float(close), 2),
        "position": {"side": side_map[sig.mode], "size": 0, "entry": round(float(close), 2)},
        "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    with open(STATUS_PATH, "w") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)
    # 追加歷史
    hist_line = {
        "time": status["updated_at"],
        "grid_mode": sig.mode,
        "confidence": sig.confidence,
        "close": round(float(close), 2),
        "reason": sig.reason,
    }
    with open(os.path.join(RUNTIME_DIR, "grid_signals.jsonl"), "a") as f:
        f.write(json.dumps(hist_line, ensure_ascii=False) + "\n")
    return status


def main():
    df = compute_indicators(load_data())
    i = len(df) - 1
    # 如果最新一根當日還沒收盤, 用倒數第二根 (更穩健)
    if df["adx"].iloc[i] != df["adx"].iloc[i]:  # NaN guard
        i -= 1
    sig = decide(df, i)
    status = write_status(sig, df["close"].iloc[i], df)
    print(f"[{status['updated_at']}] {SYMBOL} 收盤 {status['last_close']}")
    print(f"網格模式: {sig.mode.upper()} (信心 {sig.confidence:.0%})")
    print(f"理由: {sig.reason}")
    print(f"指標: {sig.indicators}")
    print(f"→ 寫入 {STATUS_PATH}")


if __name__ == "__main__":
    main()
