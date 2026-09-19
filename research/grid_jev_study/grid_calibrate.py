#!/usr/bin/env python3
"""Stage 0: 校準測量工具。必須重現 docstring 記載的
    corr(natr, 未來30天淨位移) = -0.594，否則後續評判全部無效。

docstring 原文：「實測 (78 個 30 天視窗)」
  natr 最低 20% 組 -> 未來 30 天淨位移中位數 21.0%
  natr 最高 20% 組 -> 未來 30 天淨位移中位數  3.6%
"""
import numpy as np, pandas as pd, itertools

df = pd.read_csv('/root/Crypto-Backtesting-Lab/research/btc_usdt_1d.csv')
df.columns = [c.lower() for c in df.columns]
dcol = 'date' if 'date' in df.columns else ('timestamp' if 'timestamp' in df.columns else df.columns[0])
df[dcol] = pd.to_datetime(df[dcol])
df = df.drop_duplicates(dcol).sort_values(dcol).reset_index(drop=True)
print(f"日線 {len(df)} 根  {df[dcol].iloc[0].date()} ~ {df[dcol].iloc[-1].date()}")

hi, lo, cl = df['high'], df['low'], df['close']
tr = pd.concat([(hi-lo), (hi-cl.shift()).abs(), (lo-cl.shift()).abs()], axis=1).max(axis=1)
atr = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
natr = (atr/cl).values
C = cl.values.astype(float)
N = len(C)

def net_disp(i, d):
    """未來 d 天淨位移（帶號，%)"""
    if i+d >= N: return None
    return (C[i+d]-C[i])/C[i]*100

def abs_disp(i, d):
    v = net_disp(i, d)
    return None if v is None else abs(v)

print(f"\n{'視窗步長':>10}{'視窗數':>8}{'corr(帶號)':>12}{'corr(絕對)':>12}")
print("-"*44)
for step in [1,2,3,5,7,10,15,30]:
    idx = [i for i in range(250, N-30, step) if not np.isnan(natr[i])]
    n_ = np.array([natr[i] for i in idx])
    sd = np.array([net_disp(i,30) for i in idx], dtype=float)
    ad = np.array([abs_disp(i,30) for i in idx], dtype=float)
    cs = np.corrcoef(n_, sd)[0,1] if len(idx)>2 else float('nan')
    ca = np.corrcoef(n_, ad)[0,1] if len(idx)>2 else float('nan')
    print(f"{step:>10}{len(idx):>8}{cs:>12.3f}{ca:>12.3f}")

print("\n=== 找視窗數 ≈78 的設定 ===")
for step in range(1,20):
    idx=[i for i in range(250,N-30,step) if not np.isnan(natr[i])]
    if 70 <= len(idx) <= 86:
        n_=np.array([natr[i] for i in idx])
        sd=np.array([net_disp(i,30) for i in idx],dtype=float)
        cs=np.corrcoef(n_,sd)[0,1]
        # 五分位
        q=np.quantile(n_,[0.2,0.8])
        low=sd[n_<=q[0]]; high=sd[n_>=q[1]]
        print(f"step={step}: n={len(idx)}  corr(帶號)={cs:+.3f}  "
              f"低natr組中位={np.median(np.abs(low)):.1f}%  高natr組中位={np.median(np.abs(high)):.1f}%")

print("\n=== 目標: corr=-0.594, 低natr組 21.0%, 高natr組 3.6% ===")
print("\n=== 全樣本（不取視窗）===")
for d in [7,14,30,60]:
    idx=[i for i in range(250,N-d) if not np.isnan(natr[i])]
    n_=np.array([natr[i] for i in idx]); sd=np.array([net_disp(i,d) for i in idx],dtype=float)
    print(f"  d={d:>3}: n={len(idx)}  corr={np.corrcoef(n_,sd)[0,1]:+.3f}")
