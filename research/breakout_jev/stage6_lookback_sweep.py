#!/usr/bin/env python3
"""Stage 6（最後一個未測槓桿）: 回看長度敏感度 + 擴張態。

假設：前幾個階段全用 Donchian 24（=2 小時）。24 根的「前高」可能只是噪音，
而更長的回看（96 根 = 8h、288 根 = 24h、576 根 = 48h）代表真正的價格關卡
—— 突破「真關卡」與突破「2小時內的小高點」是不同性質的事件。

同時補測擴張態（bw_rank > 70）：Stage 5 只測了壓縮態（< 30），沒測另一端。

若本階段也全負 → 5m 突破的所有維度已窮盡，目標確定結束。
"""
import sys
sys.path.insert(0,'/root/Crypto-Backtesting-Lab')
import numpy as np, pandas as pd, os

TF='5min'; ATR_N=14; MAX_HOLD=48; FEE=0.0005

def load_5m(path):
    M=pd.read_parquet(path)
    dc=[c for c in M.columns if c.lower() in ('dt','timestamp','time','date')][0]
    M[dc]=pd.to_datetime(M[dc]); M=M.sort_values(dc).set_index(dc)
    agg={'open':'first','high':'max','low':'min','close':'last'}
    if 'volume' in M.columns: agg['volume']='sum'
    out=M.resample(TF).agg(agg).dropna(subset=['open','high','low','close'])
    if 'volume' not in out.columns: out['volume']=np.nan
    return out

def add_ind(df, lookback):
    df=df.copy(); hi,lo,cl=df['high'],df['low'],df['close']
    tr=pd.concat([(hi-lo),(hi-cl.shift()).abs(),(lo-cl.shift()).abs()],axis=1).max(axis=1)
    df['atr']=tr.ewm(alpha=1/ATR_N,adjust=False,min_periods=ATR_N).mean()
    df['don_hi']=hi.rolling(lookback).max().shift(1)
    df['don_lo']=lo.rolling(lookback).min().shift(1)
    df['brk_up']=cl>df['don_hi']; df['brk_dn']=cl<df['don_lo']
    df['brk_str']=np.where(df['brk_up'],(cl-df['don_hi'])/df['atr'],
                  np.where(df['brk_dn'],(df['don_lo']-cl)/df['atr'],np.nan))
    ma=cl.rolling(20).mean(); sd=cl.rolling(20).std()
    bw=(4*sd)/ma
    df['bw_rank']=bw.rolling(96).apply(lambda x:(x[-1]<=x).mean()*100, raw=True)
    return df

def bt(df, signals, stop_atr, target_atr, fee, max_hold=MAX_HOLD):
    n=len(df)
    o=df['open'].values; h=df['high'].values; l=df['low'].values; c=df['close'].values
    atr=df['atr'].values
    trades=[]; busy=-1
    for idx,d in signals:
        if idx<=busy or idx+1>=n or np.isnan(atr[idx]): continue
        e=idx+1; entry=o[e]; a=atr[idx]
        if a<=0 or entry<=0: continue
        stop=entry-d*stop_atr*a; tgt=entry+d*target_atr*a
        ex=None; ei=None
        for j in range(e,min(e+max_hold,n)):
            if d>0:
                if l[j]<=stop: ex,ei=stop,j; break
                if h[j]>=tgt:  ex,ei=tgt,j; break
            else:
                if h[j]>=stop: ex,ei=stop,j; break
                if l[j]<=tgt:  ex,ei=tgt,j; break
        if ex is None: ei=min(e+max_hold-1,n-1); ex=c[ei]
        trades.append({'pnl':d*(ex-entry)/entry*100-2*fee*100,
                       'gross':d*(ex-entry)/entry*100})
        busy=ei
    return pd.DataFrame(trades)

ASSETS=[('BTC','/root/gridlab/btc_1m.parquet'),('APT','/root/gridlab/apt_1m.parquet'),
        ('SUI','/root/gridlab/sui_1m.parquet'),('FIL','/root/gridlab/fil_1m.parquet'),
        ('BCH','/root/gridlab/bch_1m.parquet')]

print("=== A. 回看長度敏感度（stop 2 / target 4）===")
print("假設：長回看 = 真關卡，短回看 = 噪音\n")
hdr=f"{'標的':>5}" + "".join(f"{'LB'+str(lb):>22}" for lb in [12,24,96,288,576])
print(hdr); print("-"*len(hdr))
best_overall=[]
for name,path in ASSETS:
    if not os.path.exists(path): continue
    raw=load_5m(path)
    line=f"{name:>5}"
    for lb in [12,24,96,288,576]:
        df=add_ind(raw,lb).dropna(subset=['atr','don_hi','don_lo'])
        if len(df)<3000: line+=f"{'—':>22}"; continue
        m=df['brk_up'].values|df['brk_dn'].values
        sigs=sorted([(int(i),1) for i in np.where(df['brk_up'].values)[0]]+
                    [(int(i),-1) for i in np.where(df['brk_dn'].values)[0]])
        if len(sigs)<100: line+=f"{'n/a':>22}"; continue
        T0=bt(df,sigs,2.0,4.0,0.0)
        g=T0['gross'].mean() if len(T0) else 0
        line+=f"{f'{len(sigs)}/{g:+.4f}':>22}"
        best_overall.append((g,name,lb,len(sigs)))
    print(line)

print("\n各組合按零費率平均排序（前 8）:")
for g,name,lb,n in sorted(best_overall, reverse=True)[:8]:
    flag=' ← 正期望' if g>0 else ''
    print(f"  {name:>4} LB={lb:<4} n={n:<6} 零費率平均 {g:+.4f}%{flag}")

print("\n=== B. 擴張態（bw_rank > 70，波動已放大）===")
print(f"{'標的':>5}{'LB':>6}{'訊號':>8}{'零費率平均':>12}{'taker平均':>11}{'勝率':>8}")
print("-"*52)
for name,path in ASSETS:
    if not os.path.exists(path): continue
    raw=load_5m(path)
    for lb in [24,96]:
        df=add_ind(raw,lb).dropna(subset=['atr','don_hi','don_lo'])
        if len(df)<3000: continue
        m=(df['bw_rank'].values>70)
        upv=np.where(df['brk_up'].values)[0]; dnv=np.where(df['brk_dn'].values)[0]
        sigs=sorted([(int(i),1) for i in upv if m[i]]+[(int(i),-1) for i in dnv if m[i]])
        if len(sigs)<100: continue
        T0=bt(df,sigs,2.0,4.0,0.0); T1=bt(df,sigs,2.0,4.0,FEE)
        print(f"{name:>5}{lb:>6}{len(sigs):>8}{T0['gross'].mean():>+12.4f}"
              f"{T1['pnl'].mean():>+11.4f}{(T1['pnl']>0).mean():>8.1%}")

print("\n=== C. 最優組合的 Jev 檢驗（若 A 段有任何正期望）===")
pos=[b for b in best_overall if b[0]>0.005]
if not pos:
    print("無任何組合達到 零費率平均 > +0.005% → 無需動用 Jev")
else:
    print(f"有 {len(pos)} 個組合零費率為正，需進一步驗證: {pos}")

print("\n=== 判讀 ===")
print("若所有 LB 組合零費率皆 ≈0 或負 → 5m 突破在回看長度維度上亦無空間")
