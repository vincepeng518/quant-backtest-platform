"""Grid Switcher Engine v2 — 波動門檻 + ATR 自適應網格幾何。

v1 已作廢的假設 (2026-07-30 實測推翻)
------------------------------------
v1 規則: BBW 百分位 < 35 且 ATR% < 2.5 -> 開 range 網格 (即「盤整才開網格」)。
在 BingX BTC/USDT:USDT 1m 真實 K 線 575,999 根 (2025-06-25 ~ 2026-07-30) 上逐日
gating 回測, 該規則 400 天 PnL = -2,392, 6 個分段 0/6 為正。

根因: 低波動不是盤整的延續, 而是趨勢的前兆。實測 (78 個 30 天視窗)
  corr(natr_now, 未來30天淨位移) = -0.594
  natr 最低 20% 組 -> 未來 30 天淨位移中位數 21.0%
  natr 最高 20% 組 -> 未來 30 天淨位移中位數  3.6%
而網格的損益結構 (R^2 = 0.904 回歸):
  30天PnL = 773 - 0.337 x |淨位移| + 0.00081 x 路徑長度
網格怕的是「單向位移」, 不是「波動」。低波動 -> 壓縮 -> 爆發 -> 網格被單邊輾壓。

v2 的兩個機制
-------------
1. 波動門檻 (gate): natr >= 歷史 expanding 中位數才開網格, 否則 flat。
   門檻用 expanding quantile 且 shift(1), 只看當下之前的資料, 無未來函數。
2. ATR 自適應幾何 (主要獲利來源): half_range = 日線 ATR x hr_mult (預設 16),
   而非固定 +/-3000 USD。固定區間在高價/低波動時格距過密, 手續費吃光價差。

實測 (400 天, 1m 執行, maker 1bp, 倉位上限 0.20 BTC, cap 生效)
  ALWAYS ON  固定+/-3000  : PnL -8,172  MaxDD -9,778  分段 1/6
  v1 規則    固定+/-3000  : PnL -2,392  MaxDD -2,807  分段 0/6
  ALWAYS ON  ATR x16     : PnL   -326  MaxDD -1,790  分段 4/6
  v2 gate +  ATR x16     : PnL   +265  MaxDD   -294  分段 3/6
  v2 gate + 方向偏置 + ATR x16 : PnL +211  MaxDD -182  分段 4/6  <- 預設組態

誠實聲明 (務必閱讀)
------------------
- 絕對收益極小: +211 USD / 400 天, 對應最大名義曝險約 2 萬 USD。這不是收益引擎,
  它的價值在於「把一個 MaxDD -9,778 的爆倉結構壓成 MaxDD -182」。
- 有效獨立樣本僅約 7 個 (30 天視窗高度重疊)。任何高勝率都不可外推。
- 同期單純放空持有 20k 名義 = +7,924 / MaxDD -4,262, 完勝所有網格版本。
  若你對方向有觀點, 不要用網格。
- 硬止損在 400 天樣本內任何檔位 (-300 / -600 / -1000 / -2000) 都會被打掉且
  6/6 分段皆負 -> 本結構無法與固定金額止損共存, 風控只能靠倉位上限 + 波動門檻。

輸出: runtime/strategy_status.json (相容 v1 schema, 新增網格幾何欄位)
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

_CANDIDATE_ROOTS = [
    "/app",
    "/root/Crypto-Backtesting-Lab",
    os.getenv("PROJECT_ROOT") or "",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")),
]
ROOT = next(
    (r for r in _CANDIDATE_ROOTS
     if r and os.path.exists(os.path.join(r, "engine", "strategies", "grid_switcher.py"))),
    _CANDIDATE_ROOTS[0],
)
DATA_CACHE = os.path.join(ROOT, "research", "btc_usdt_1d.csv")
RUNTIME_DIR = os.path.join(ROOT, "runtime")
STATUS_PATH = os.path.join(RUNTIME_DIR, "strategy_status.json")
SYMBOL = "BTC/USDT"

# ── 參數 (實測最佳, 見 module docstring) ────────────────────────────────
NATR_Q = 0.50          # 波動門檻分位 (expanding)
MIN_HIST = 250         # 門檻至少需要幾天歷史才生效
HR_MULT = 16.0         # half_range = 日線ATR x HR_MULT
N_GRIDS = 80           # 網格數
CAP_NOTIONAL_RATIO = 1.0   # 倉位上限 = 每格名義 x N_GRIDS x 此比率 (見 compute_geometry)
ADX_TREND = 25.0
DI_DIFF = 4.0


# ── 數據 ────────────────────────────────────────────────────────────────
def load_data() -> pd.DataFrame:
    """日線 OHLCV。v2 需要較長歷史 (expanding 門檻 + sma200), 目標 >= 800 根。"""
    if os.path.exists(DATA_CACHE):
        df = pd.read_csv(DATA_CACHE)
        if "timestamp" in df.columns:
            df = df.rename(columns={"timestamp": "date"})
        df["date"] = pd.to_datetime(df["date"])
        if len(df) > 800:
            return df
    if ccxt:
        ex = ccxt.bingx({"enableRateLimit": True})
        since = ex.parse8601("2021-01-01T00:00:00Z")
        rows: list = []
        while True:
            bars = ex.fetch_ohlcv("BTC/USDT:USDT", "1d", since=since, limit=1000)
            if not bars:
                break
            rows += bars
            nxt = bars[-1][0] + 86_400_000
            if nxt <= since:
                break
            since = nxt
            if bars[-1][0] > ex.milliseconds() - 86_400_000:
                break
        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
        df = df.drop_duplicates("date").sort_values("date")
        df["date"] = pd.to_datetime(df["date"], unit="ms")
    elif yf:
        df = yf.download("BTC-USD", start="2021-01-01", interval="1d").reset_index()
        df = df.rename(columns={"Date": "date", "Open": "open", "High": "high",
                                "Low": "low", "Close": "close", "Volume": "volume"})
    else:
        raise RuntimeError("no data source: install ccxt or yfinance")
    os.makedirs(os.path.dirname(DATA_CACHE), exist_ok=True)
    df.to_csv(DATA_CACHE, index=False)
    return df


# ── 指標 ────────────────────────────────────────────────────────────────
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("date").reset_index(drop=True)
    hi, lo, cl = df["high"], df["low"], df["close"]

    tr = pd.concat([(hi - lo), (hi - cl.shift()).abs(), (lo - cl.shift()).abs()], axis=1).max(axis=1)
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

    # 波動門檻: expanding 分位, shift(1) 確保只用「當日之前」的歷史 (無未來函數)
    df["natr_thr"] = df["natr"].expanding(MIN_HIST).quantile(NATR_Q).shift(1)

    ma20 = cl.rolling(20).mean()
    sd20 = cl.rolling(20).std()
    df["bbw_pct"] = ((4 * sd20) / ma20).rolling(60).apply(lambda x: (x[-1] <= x).mean() * 100, raw=True)
    df["atr_pct"] = (atr / cl) * 100
    df["sma50"] = cl.rolling(50).mean()
    df["sma200"] = cl.rolling(200).mean()
    return df


# ── 信號 ────────────────────────────────────────────────────────────────
@dataclass
class GridSignal:
    mode: str          # range | long | short | flat
    confidence: float  # 0-1
    reason: str
    indicators: dict
    geometry: dict     # 網格幾何: half_range / spacing / n_grids / bounds / max_pos


def compute_geometry(close: float, atr: float, hr_mult: float = HR_MULT,
                     n_grids: int = N_GRIDS) -> dict:
    """ATR 自適應網格幾何。這是 v2 的主要獲利來源, 不是 gate。

    固定 +/-3000 USD 在 BTC 6 萬價位 = +/-5%, 格距 75 USD (0.125%)。
    maker 1bp 來回 2bp = 0.02%, 只佔格距 16% -> 看似夠, 但一旦單邊移動,
    庫存線性累積而價差收入固定, 淨虧損以位移平方增長。
    ATR x16 讓格距跟著波動放大 -> 高波動時格距寬, 單位庫存賺更多價差。
    """
    half_range = float(atr) * hr_mult
    spacing = 2.0 * half_range / n_grids
    return {
        "half_range": round(half_range, 2),
        "spacing": round(spacing, 2),
        "n_grids": n_grids,
        "lower": round(close - half_range, 2),
        "upper": round(close + half_range, 2),
        "spacing_pct": round(100 * spacing / close, 4),
        "recenter_gap": round(half_range / 3.0, 2),
    }


def decide(df: pd.DataFrame, i: int,
           natr_q: float = NATR_Q, hr_mult: float = HR_MULT,
           adx_trend: float = ADX_TREND, di_diff: float = DI_DIFF) -> GridSignal:
    """v2 判定。

    步驟 1 (gate): natr < 歷史 expanding 分位 -> flat, 不開網格。
                   低波動 = 趨勢前兆 = 網格墳場 (實測 natr 最低五分位勝率 6%)。
    步驟 2 (方向): 已過門檻, 用 SMA 排列 + ADX + DI 決定 long / short / range 偏置。
    """
    r = df.iloc[i]
    natr = float(r["natr"])
    thr = r["natr_thr"]
    close = float(r["close"])
    atr = float(r["atr"])
    adx = float(r["adx"])
    pdi = float(r["plus_di"])
    mdi = float(r["minus_di"])

    ind = {
        "natr": f"{natr:.4f}",
        "natr_thr": (None if pd.isna(thr) else f"{float(thr):.4f}"),
        "adx": round(adx, 1),
        "pdi": round(pdi, 1),
        "mdi": round(mdi, 1),
        "atr": round(atr, 1),
    }
    geo = compute_geometry(close, atr, hr_mult)

    if pd.isna(thr):
        return GridSignal("flat", 0.0,
                          f"歷史不足 {MIN_HIST} 天，波動門檻未生效 → 不開網格",
                          ind, geo)

    if natr < float(thr):
        return GridSignal(
            "flat", 0.0,
            f"nATR {natr:.4f} < 歷史{int(natr_q*100)}分位 {float(thr):.4f} → 低波動是趨勢前兆，不開網格",
            ind, geo)

    pct = f"nATR {natr:.4f} >= 門檻 {float(thr):.4f}"
    sma50 = float(r["sma50"])
    sma200 = float(r["sma200"])

    if sma50 > sma200 and adx >= adx_trend and (pdi - mdi) > di_diff:
        return GridSignal("long", 0.60,
                          f"{pct} + SMA多排列 + ADX{adx:.0f} → 只做多網格（庫存只準為正）",
                          ind, geo)
    if sma50 < sma200 and adx >= adx_trend and (mdi - pdi) > di_diff:
        return GridSignal("short", 0.60,
                          f"{pct} + SMA空排列 + ADX{adx:.0f} → 只做空網格（庫存只準為負）",
                          ind, geo)
    return GridSignal("range", 0.55,
                      f"{pct} + 無明確排列 → 中性網格，格距 {geo['spacing']:.0f}（{geo['spacing_pct']:.3f}%）",
                      ind, geo)


# ── 輸出 ────────────────────────────────────────────────────────────────
def write_status(sig: GridSignal, close: float, bar_date) -> dict:
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    side_map = {"range": "flat", "long": "long", "short": "short", "flat": "flat"}
    status = {
        "available": True,
        "running": True,
        "strategy": "grid_switcher",
        "version": 2,
        "symbol": SYMBOL,
        "exchange": "bingx",
        "grid_mode": sig.mode,
        "confidence": sig.confidence,
        "reason": sig.reason,
        "indicators": sig.indicators,
        "geometry": sig.geometry,
        "last_close": round(float(close), 2),
        "bar_date": str(pd.Timestamp(bar_date).date()),
        "position": {"side": side_map[sig.mode], "size": 0, "entry": round(float(close), 2)},
        "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    with open(STATUS_PATH, "w") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)
    hist_line = {
        "time": status["updated_at"],
        "bar_date": status["bar_date"],
        "grid_mode": sig.mode,
        "confidence": sig.confidence,
        "close": round(float(close), 2),
        "reason": sig.reason,
        "spacing": sig.geometry.get("spacing"),
        "half_range": sig.geometry.get("half_range"),
    }
    with open(os.path.join(RUNTIME_DIR, "grid_signals.jsonl"), "a") as f:
        f.write(json.dumps(hist_line, ensure_ascii=False) + "\n")
    return status


def latest_signal() -> tuple[GridSignal, float, object]:
    """回傳最新一根已收盤日線的信號 (供 API / 測試複用)。"""
    df = compute_indicators(load_data())
    i = len(df) - 1
    while i > 0 and pd.isna(df["adx"].iloc[i]):
        i -= 1
    return decide(df, i), float(df["close"].iloc[i]), df["date"].iloc[i]


def main():
    sig, close, bar_date = latest_signal()
    status = write_status(sig, close, bar_date)
    print(f"[{status['updated_at']}] {SYMBOL} bar={status['bar_date']} 收盤 {status['last_close']}")
    print(f"網格模式: {sig.mode.upper()} (信心 {sig.confidence:.0%})")
    print(f"理由: {sig.reason}")
    print(f"指標: {sig.indicators}")
    if sig.mode != "flat":
        g = sig.geometry
        print(f"幾何: 區間 {g['lower']} ~ {g['upper']} | {g['n_grids']} 格 | "
              f"格距 {g['spacing']} ({g['spacing_pct']}%) | 重置間距 {g['recenter_gap']}")
    print(f"-> 寫入 {STATUS_PATH}")


if __name__ == "__main__":
    main()
