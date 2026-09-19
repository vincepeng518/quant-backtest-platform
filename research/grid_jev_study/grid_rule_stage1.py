#!/usr/bin/env python3
"""Stage 1: 複製 grid_switcher 規則，跑出決策分布，圈出「爭議棒」。

爭議棒定義（規則邊緣地帶，規則在此最可能瞎猜）：
  A. gate 邊緣：natr 與門檻差距在 ±8% 內 → 「開不開」很勉強
  B. 方向邊緣：已過 gate，但 ADX 或 DI 差距接近閾值 → long/short/range 難分
"""
import sys, json
sys.path.insert(0, '/root/Crypto-Backtesting-Lab')
import pandas as pd, numpy as np

from engine.strategies.grid_switcher import (
    load_data, compute_indicators, decide, NATR_Q, ADX_TREND, DI_DIFF, MIN_HIST
)

df = compute_indicators(load_data())
print(f"資料：{len(df)} 根日線  {df['date'].iloc[0].date()} ~ {df['date'].iloc[-1].date()}")

rows = []
for i in range(len(df)):
    r = df.iloc[i]
    if pd.isna(r['natr_thr']) or pd.isna(r['adx']):
        continue
    sig = decide(df, i)
    natr = float(r['natr']); thr = float(r['natr_thr'])
    adx = float(r['adx']); pdi = float(r['plus_di']); mdi = float(r['minus_di'])
    rows.append({
        'i': i, 'date': str(r['date'].date()), 'close': float(r['close']),
        'natr': natr, 'thr': thr, 'adx': adx, 'pdi': pdi, 'mdi': mdi,
        'atr': float(r['atr']), 'sma50': float(r['sma50']), 'sma200': float(r['sma200']),
        'mode': sig.mode,
    })

D = pd.DataFrame(rows)
print(f"有效 bar（門檻已生效）：{len(D)}\n")

print("=== 規則決策分布 ===")
print(D['mode'].value_counts().to_string())

# A. gate 邊緣
D['gate_margin'] = (D['natr'] - D['thr']) / D['thr']      # >0 過門檻
D['gate_contested'] = D['gate_margin'].abs() <= 0.08

# B. 方向邊緣（只在過 gate 的 bar 上有意義）
passed = D[D['gate_margin'] > 0].copy()
passed['di_diff'] = (passed['pdi'] - passed['mdi']).abs()
passed['adx_margin'] = (passed['adx'] - ADX_TREND).abs()
passed['di_margin'] = (passed['di_diff'] - DI_DIFF).abs()
passed['dir_contested'] = (passed['adx_margin'] <= 3.0)
D = D.merge(passed[['i','dir_contested']], on='i', how='left')
D['dir_contested'] = D['dir_contested'].fillna(False)

print(f"\n=== 爭議棒 ===")
print(f"A. gate 邊緣 (|natr-thr|/thr <= 8%)      : {D['gate_contested'].sum():4d} 根")
print(f"B. 方向邊緣 (ADX 距閾值 <= 3)            : {D['dir_contested'].sum():4d} 根")
both = D[D['gate_contested'] | D['dir_contested']]
print(f"合計去重                                 : {len(both):4d} 根  ({len(both)/len(D)*100:.0f}% of {len(D)})")

print(f"\n=== 規則在 gate 邊緣的決策（最不穩的地帶）===")
print(D[D['gate_contested']]['mode'].value_counts().to_string())

print(f"\n=== gate 邊緣且規則判 flat 的樣本（規則說不開，真的對嗎？）===")
s = D[D['gate_contested'] & (D['mode']=='flat')].head(8)
print(s[['date','close','natr','thr','adx','pdi','mdi','mode']].to_string(index=False))

D.to_csv('/tmp/grid_rule_decisions.csv', index=False)
print(f"\n已存 /tmp/grid_rule_decisions.csv（{len(D)} 根）")
