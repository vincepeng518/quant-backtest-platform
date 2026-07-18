"""Trend Fusion — 多指標投票融合，輸出 3 態信號 (long/short/flat)。

設計依據 (research/ 三份報告結論):
  A (ADX/DI):  方向預測接近隨機, 但 ADX<20 是可靠「平盤」標誌, ADX>=25 是「有趨勢」標誌
  B (BBW/KC):  盤整精確率 77% (BBW百分位<35 & ATR<2.5%), 但召回率低 → 適合「確認盤整」而非「抓盤整」
  C (Donchian): 突破+SMA排列 方向準確率 52-56%, 是三者中最好的趨勢觸發器

融合邏輯 (針對「合約網格自動切換」場景 — 寧可錯過不可亂切):
  flat (盤整網格): B 盤整信號 AND A.ADX<adx_flat  → 雙重確認才開盤整網格
  long (看多網格): C 突破上軌 AND A.ADX>=adx_trend AND +DI>-DI → 三重確認
  short(看空網格): C 突破下軌 AND A.ADX>=adx_trend AND -DI>+DI → 三重確認
  其餘 → flat (保守: 不確定就當盤整, 但網格方向待定)

對照模式:
  - majority: 三家族各出一票, 2/3 才定方向
  - OR:       任一看多即看多 (激進, 抓趨勢但不怕亂切)
  - strict:   上述融合邏輯 (最嚴, 適合網格切換)

回測: 對照 t+5 實際漲跌, 比較三模式的方向準確率 + 盤整識別率 + 綜合 score。
"""

from __future__ import annotations

import os
import sys
import datetime as dt
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

CACHE = os.path.join(os.path.dirname(__file__), "btc_usdt_1d.csv")
SYMBOL = "BTC/USDT"


# ── 數據 ────────────────────────────────────────────────────────────────
def load_data() -> pd.DataFrame:
    if os.path.exists(CACHE):
        df = pd.read_csv(CACHE)
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
    df.to_csv(CACHE, index=False)
    return df


# ── 指標 ────────────────────────────────────────────────────────────────
def _wilder_smooth(series: pd.Series, n: int) -> pd.Series:
    out = series.copy().astype(float)
    for i in range(1, len(out)):
        out.iloc[i] = (out.iloc[i - 1] * (n - 1) + series.iloc[i]) / n
    return out


def compute_indicators(df: pd.DataFrame):
    hi, lo, cl = df["high"], df["low"], df["close"]
    # A: ADX/DI (standard Wilder, pandas-native)
    up_move = hi.diff()
    down_move = lo.diff().mul(-1)
    plus_dm = up_move.clip(lower=0).where(up_move > down_move, 0.0)
    minus_dm = down_move.clip(lower=0).where(down_move > up_move, 0.0)
    tr = pd.concat([
        (hi - lo),
        (hi - cl.shift()).abs(),
        (lo - cl.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1/14, adjust=False, min_periods=14).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1/14, adjust=False, min_periods=14).mean() / atr
    di_sum = (plus_di + minus_di).replace(0, 1e-9)
    dx = 100 * (plus_di - minus_di).abs() / di_sum
    adx = dx.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    df["adx"] = adx; df["plus_di"] = plus_di; df["minus_di"] = minus_di; df["atr"] = atr

    # B: BBW + ATR%
    ma20 = cl.rolling(20).mean()
    sd20 = cl.rolling(20).std()
    upper = ma20 + 2 * sd20; lower = ma20 - 2 * sd20
    bbw = (upper - lower) / ma20
    df["bbw_pct"] = bbw.rolling(60).apply(lambda x: (x[-1] <= x).mean() * 100, raw=True)
    df["atr_pct"] = (atr / cl) * 100

    # C: Donchian (shift 1 to avoid self-inclusion) + SMA
    dc_hi = cl.shift(1).rolling(20).max(); dc_lo = cl.shift(1).rolling(20).min()
    df["dc_hi"] = dc_hi; df["dc_lo"] = dc_lo
    df["sma50"] = cl.rolling(50).mean(); df["sma200"] = cl.rolling(200).mean()
    return df


# ── 單指標信號 ──────────────────────────────────────────────────────────
def sig_a(df, i, adx_flat=20, adx_trend=25, di_diff=4.0) -> int:
    """ADX/DI: +1 多 / -1 空 / 0 平"""
    adx = df["adx"].iloc[i]; pdi = df["plus_di"].iloc[i]; mdi = df["minus_di"].iloc[i]
    if adx < adx_flat:
        return 0
    if adx >= adx_trend and (pdi - mdi) > di_diff:
        return 1
    if adx >= adx_trend and (mdi - pdi) > di_diff:
        return -1
    return 0


def sig_b(df, i, bbw_pct=35.0, atr_pct=2.5) -> int:
    """BBW/KC: 收斂=平盤(0), 貼上帶=+1, 貼下帶=-1 (簡化: 用 BBW 擴張方向)"""
    bp = df["bbw_pct"].iloc[i]; ap = df["atr_pct"].iloc[i]
    if bp < bbw_pct and ap < atr_pct:
        return 0  # 盤整
    # 趨勢方向: 用收盤相對 20MA 位置
    cl = df["close"].iloc[i]; ma20 = df["close"].rolling(20).mean().iloc[i]
    return 1 if cl > ma20 else -1


def sig_c(df, i) -> int:
    """Donchian+SMA: 突破上軌且多排列=+1, 突破下軌且空排列=-1, 否則 0"""
    cl = df["close"].iloc[i]
    if cl > df["dc_hi"].iloc[i] and df["sma50"].iloc[i] > df["sma200"].iloc[i]:
        return 1
    if cl < df["dc_lo"].iloc[i] and df["sma50"].iloc[i] < df["sma200"].iloc[i]:
        return -1
    return 0


# ── 融合模式 ────────────────────────────────────────────────────────────
def fuse_strict(df, i) -> int:
    """最嚴: 網格切換適用。盤整雙確認, 趨勢三確認。"""
    a = sig_a(df, i); b = sig_b(df, i); c = sig_c(df, i)
    # flat: B 盤整 AND A 弱趨勢
    if b == 0 and a == 0:
        return 0
    # long: C 突破 AND A 趨勢多
    if c == 1 and a == 1:
        return 1
    if c == -1 and a == -1:
        return -1
    return 0  # 保守: 不確定當盤整


def fuse_majority(df, i) -> int:
    a, b, c = sig_a(df, i), sig_b(df, i), sig_c(df, i)
    votes = [v for v in (a, b, c) if v != 0]
    if not votes:
        return 0
    if votes.count(1) >= 2:
        return 1
    if votes.count(-1) >= 2:
        return -1
    return 0


def fuse_or(df, i) -> int:
    a, b, c = sig_a(df, i), sig_b(df, i), sig_c(df, i)
    if 1 in (a, b, c):
        return 1
    if -1 in (a, b, c):
        return -1
    return 0


# ── 回測 ────────────────────────────────────────────────────────────────
def backtest(df, fuse_fn, n_fwd=5):
    sigs = []
    for i in range(len(df) - n_fwd):
        if df[["adx", "bbw_pct", "dc_hi", "sma200"]].iloc[i].isna().any():
            sigs.append(0)
            continue
        sigs.append(fuse_fn(df, i))
    sigs = pd.Series(sigs)
    fwd_ret = df["close"].shift(-n_fwd) / df["close"] - 1
    fwd_ret = fwd_ret.iloc[:len(sigs)]

    # 方向準確率
    dir_mask = sigs != 0
    dir_correct = ((sigs == 1) & (fwd_ret > 0)) | ((sigs == -1) & (fwd_ret < 0))
    dir_acc = dir_correct[dir_mask].mean() if dir_mask.any() else 0.0
    # 盤整識別率: 信號 flat 且 |ret| <= 3%
    flat_mask = sigs == 0
    flat_correct = flat_mask & (fwd_ret.abs() <= 0.03)
    flat_acc = flat_correct.sum() / flat_mask.sum() if flat_mask.any() else 0.0
    # 綜合 score: 方向日正確 + 盤整日正確 佔比
    total = len(sigs)
    score = (dir_correct.sum() + flat_correct.sum()) / total if total else 0.0
    return {
        "n": total,
        "n_long": int((sigs == 1).sum()),
        "n_short": int((sigs == -1).sum()),
        "n_flat": int((sigs == 0).sum()),
        "dir_acc": round(float(dir_acc), 4),
        "flat_acc": round(float(flat_acc), 4),
        "score": round(float(score), 4),
    }


def main():
    df = compute_indicators(load_data())
    print(f"樣本: {len(df)} 根日線\n")
    modes = {
        "strict (網格切換推薦)": fuse_strict,
        "majority (多數投票)": fuse_majority,
        "OR (激進)": fuse_or,
    }
    results = {}
    for name, fn in modes.items():
        r = backtest(df, fn)
        results[name] = r
        print(f"【{name}】")
        print(f"  long={r['n_long']} short={r['n_short']} flat={r['n_flat']}")
        print(f"  方向準確率={r['dir_acc']:.3f}  盤整識別率={r['flat_acc']:.3f}  綜合score={r['score']:.3f}\n")

    # 單一最佳指標對照
    print("【單一指標基準】")
    for nm, fn in [("A:ADX/DI", sig_a), ("B:BBW", sig_b), ("C:Donchian", sig_c)]:
        r = backtest(df, fn)
        print(f"  {nm}: 方向={r['dir_acc']:.3f} 盤整={r['flat_acc']:.3f} score={r['score']:.3f}")


if __name__ == "__main__":
    main()
