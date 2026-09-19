#!/usr/bin/env python3
"""產出 5m CSV 供標準優化管線使用。

來源：/root/gridlab/{btc,fil}_1m.parquet（1m 重採樣為 5m）
輸出：data/csv/BTC_USDT_5m.csv / FIL_USDT_5m.csv
格式：timestamp,open,high,low,close,volume（與既有 data/csv/*.csv 一致）
"""
import os
import pandas as pd

OUT_DIR = '/root/Crypto-Backtesting-Lab/data/csv'
SRC = [('BTC_USDT', '/root/gridlab/btc_1m.parquet'),
       ('FIL_USDT', '/root/gridlab/fil_1m.parquet')]

for tag, path in SRC:
    if not os.path.exists(path):
        print(f"{tag}: 來源不存在 {path}")
        continue
    M = pd.read_parquet(path)
    dc = [c for c in M.columns if c.lower() in ('dt', 'timestamp', 'time', 'date')][0]
    M[dc] = pd.to_datetime(M[dc])
    M = M.sort_values(dc).set_index(dc)
    M.columns = [c.lower() for c in M.columns]

    agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
    if 'volume' in M.columns:
        agg['volume'] = 'sum'
    out = M.resample('5min').agg(agg).dropna(subset=['open', 'high', 'low', 'close'])
    if 'volume' not in out.columns:
        out['volume'] = 0.0
    out = out.reset_index()
    out = out.rename(columns={out.columns[0]: 'timestamp'})
    out = out[['timestamp', 'open', 'high', 'low', 'close', 'volume']]

    dest = os.path.join(OUT_DIR, f'{tag}_5m.csv')
    out.to_csv(dest, index=False)
    print(f"{tag}: {len(out):,} 根 5m  {out['timestamp'].iloc[0]} ~ {out['timestamp'].iloc[-1]}")
    print(f"  → {dest}  ({os.path.getsize(dest)/1024:.0f} KB)")
