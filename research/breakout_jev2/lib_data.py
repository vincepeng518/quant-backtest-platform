"""資料載入與特徵計算。所有特徵必須無未來函數。"""
from __future__ import annotations

import os

import pandas as pd

CSV_DIR = "/root/Crypto-Backtesting-Lab/data/csv"
ATR_N = 14
BARS_PER_YEAR_5M = 105_120  # 365 * 24 * 12


def load_5m(tag: str) -> pd.DataFrame:
    path = os.path.join(CSV_DIR, f"{tag}_5m.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} 不存在，先跑 make_5m_csv.py")
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.sort_values("timestamp").reset_index(drop=True)


def add_atr(df: pd.DataFrame, n: int = ATR_N) -> pd.DataFrame:
    """Wilder ATR（與 ewm(alpha=1/n) 等價）。"""
    out = df.copy()
    hi, lo, cl = out["high"], out["low"], out["close"]
    tr = pd.concat([hi - lo, (hi - cl.shift()).abs(), (lo - cl.shift()).abs()], axis=1).max(axis=1)
    out["atr"] = tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    return out


def prior_extremes(df: pd.DataFrame, lookback: int):
    """前 lookback 根（不含當根）的最高/最低。回傳 (hi, lo) 兩個 Series。"""
    hi = df["high"].rolling(lookback).max().shift(1)
    lo = df["low"].rolling(lookback).min().shift(1)
    return hi, lo


def add_features(df: pd.DataFrame, lookback: int = 576) -> pd.DataFrame:
    out = add_atr(df)
    out["don_hi"], out["don_lo"] = prior_extremes(out, lookback)
    out["ret_1"] = out["close"].pct_change(1) * 100
    out["ret_12"] = out["close"].pct_change(12) * 100
    out["ret_48"] = out["close"].pct_change(48) * 100
    return out
