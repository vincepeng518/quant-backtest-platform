#!/usr/bin/env python3
"""1m parquet -> 5m CSV，供回測管線使用。

來源：/root/gridlab/{btc,apt,sui,fil,bch}_1m.parquet（欄位 dt/open/high/low/close/vol|volume）
輸出：data/csv/<TAG>_5m.csv  欄位 timestamp,open,high,low,close,volume
"""
from __future__ import annotations

import os

import pandas as pd

OUT_DIR = "/root/Crypto-Backtesting-Lab/data/csv"
SRC = [
    ("BTC_USDT", "/root/gridlab/btc_1m.parquet"),
    ("APT_USDT", "/root/gridlab/apt_1m.parquet"),
    ("SUI_USDT", "/root/gridlab/sui_1m.parquet"),
    ("FIL_USDT", "/root/gridlab/fil_1m.parquet"),
    ("BCH_USDT", "/root/gridlab/bch_1m.parquet"),
]


def resample_5m(raw: pd.DataFrame) -> pd.DataFrame:
    """1m -> 5m。回傳標準六欄格式。"""
    df = raw.copy()
    df.columns = [c.lower() for c in df.columns]
    dc = next(c for c in ("dt", "timestamp", "time", "date") if c in df.columns)
    df[dc] = pd.to_datetime(df[dc])
    df = df.sort_values(dc).set_index(dc)
    vol_col = "volume" if "volume" in df.columns else "vol"
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", vol_col: "sum"}
    out = df.resample("5min").agg(agg).dropna(subset=["open", "high", "low", "close"])
    out = out.rename(columns={vol_col: "volume"}).reset_index()
    out = out.rename(columns={out.columns[0]: "timestamp"})
    return out[["timestamp", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def main() -> None:
    for tag, path in SRC:
        if not os.path.exists(path):
            print(f"{tag}: 來源不存在 {path}")
            continue
        out = resample_5m(pd.read_parquet(path))
        dest = os.path.join(OUT_DIR, f"{tag}_5m.csv")
        out.to_csv(dest, index=False)
        print(f"{tag}: {len(out):,} 根  {out['timestamp'].iloc[0]} ~ {out['timestamp'].iloc[-1]}")
        print(f"  -> {dest} ({os.path.getsize(dest) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
