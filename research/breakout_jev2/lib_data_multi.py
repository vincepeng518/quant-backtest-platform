"""多時間級別資料載入。

資料源盤點（2026-09-20）：
  4h：bxdata_oos/*_4h.json  2018-2021（3.6 年）  + bxdata/*_4h.json  2021-2026（5.0 年）
      → 兩段**完全不重疊**，可當真正獨立的樣本外期間。這是本輪最重要的資料優勢。
  1h：okx_data_5m/*_5m.csv（443 天）resample 12x；gridlab/*_1m.parquet（最長 400 天）resample 60x
  1d：bxdata/*_1d.json（5 年）

幣安 kline 欄位：[openTime, open, high, low, close, volume, closeTime, quoteVol, trades, ...]
"""
from __future__ import annotations

import glob
import json
import os

import pandas as pd

BYBIT_4H = "/root/bxdata"
BYBIT_OOS_4H = "/root/bxdata_oos"
BYBIT_1D = "/root/bxdata"
OKX_5M = "/root/okx_data_5m"
GRIDLAB = "/root/gridlab"


def _from_binance_json(path: str) -> pd.DataFrame:
    raw = json.load(open(path))
    df = pd.DataFrame(raw, columns=[
        "open_time", "open", "high", "low", "close", "volume", "close_time",
        "quote_volume", "trades", "taker_base", "taker_quote", "ignore"][:len(raw[0])])
    df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms")
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[["timestamp", "open", "high", "low", "close", "volume"]].dropna() \
             .sort_values("timestamp").reset_index(drop=True)


def load_4h(symbol: str, segment: str = "long") -> pd.DataFrame:
    """segment: 'recent'（2021-2026 5年）| 'oos'（2018-2021 3.6年）| 'long'（拼接全部）"""
    if segment == "recent":
        return _from_binance_json(f"{BYBIT_4H}/{symbol}_4h.json")
    if segment == "oos":
        p = f"{BYBIT_OOS_4H}/{symbol}_4h.json"
        if not os.path.exists(p):
            raise FileNotFoundError(p)
        return _from_binance_json(p)
    a = load_4h(symbol, "oos")
    b = load_4h(symbol, "recent")
    return pd.concat([a, b], ignore_index=True).drop_duplicates("timestamp") \
             .sort_values("timestamp").reset_index(drop=True)


def load_1d(symbol: str) -> pd.DataFrame:
    return _from_binance_json(f"{BYBIT_1D}/{symbol}_1d.json")


def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    out = df.set_index("timestamp").resample(rule).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna(subset=["open", "high", "low", "close"]).reset_index()
    return out


def load_5m(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df[["timestamp", "open", "high", "low", "close", "volume"]] \
             .sort_values("timestamp").reset_index(drop=True)


def load_1h_from_5m(usdt_tag: str) -> pd.DataFrame:
    """okx_data_5m/<TAG>_USDT_5m.csv -> 1h（443 天）"""
    return _resample(load_5m(f"{OKX_5M}/{usdt_tag}_USDT_5m.csv"), "1h")


def load_1h_from_gridlab(name: str) -> pd.DataFrame:
    """gridlab/<name>_1m.parquet -> 1h"""
    m = pd.read_parquet(f"{GRIDLAB}/{name}_1m.parquet")
    m.columns = [c.lower() for c in m.columns]
    dc = next(c for c in ("dt", "timestamp", "time", "date") if c in m.columns)
    m[dc] = pd.to_datetime(m[dc])
    vol = "volume" if "volume" in m.columns else "vol"
    m = m.rename(columns={dc: "timestamp", vol: "volume"})
    return _resample(m[["timestamp", "open", "high", "low", "close", "volume"]], "1h")


def available_4h(segment: str = "long") -> list[str]:
    a = glob.glob(f"{BYBIT_4H}/*_4h.json")
    syms = {os.path.basename(p)[:-8] for p in a}
    if segment in ("oos", "long"):
        b = glob.glob(f"{BYBIT_OOS_4H}/*_4h.json")
        syms &= {os.path.basename(p)[:-8] for p in b}
    return sorted(syms)


def available_1h() -> list[str]:
    fs = glob.glob(f"{OKX_5M}/*_5m.csv")
    return sorted(os.path.basename(p).replace("_USDT_5m.csv", "") for p in fs)


BARS_PER_YEAR = {"4h": 2190.0, "1h": 8760.0, "1d": 365.0}
