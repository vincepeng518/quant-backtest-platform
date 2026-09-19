#!/usr/bin/env python3
"""Stage 5: 在 5m 框架內窮盡兩個還沒測的槓桿。

  A. 多標的掃描 — BTC 5m 可能特別有效率，apt/sui/fil/bch 的 5m 結構或許不同
  B. 新變體：壓縮後突破（squeeze breakout）
     一般突破 = 價格破前高。壓縮突破 = 波動先收縮到極低，再突破。
     這是不同的訊號（選擇權市場稱 vol compression → expansion），
     且與 grid_switcher「低波動是趨勢前兆」的實證同源。

判準同前：零費率看訊號本身有沒有 edge；有 edge 才值得動用 Jev。
"""
import sys
sys.path.insert(0,'/root/Crypto-Backtesting-Lab')
import numpy as np, pandas as pd, glob, os

TF='5min'; LOOKBACK=24; ATR_N=14; MAX_HOLD=48
FEE_TAKER=0.0005

def load_5m(path):
    M=pd.read_parquet(path)
    dc=[c for c in M.columns if c.lower() in ('dt','timestamp','time','date')][0]
    M[dc]=pd.to_datetime(M[dc]); M=M.sort_values(dc).set_index(dc)
    agg={'open':'first','high':'max','low':'min','close':'last'}
    if 'volume' in M.columns:
        agg['volume']='sum'
    out=M.resample(TF).agg(agg).dropna(subset=['open','high','low','close'])
    if 'volume' not in out.columns:
        out['volume']=np.nan
    return out

def add_ind(df):
    df=df.copy(); hi,lo,cl=df['high'],df['low'],df['close']
    tr=pd.concat([(hi-lo),(hi-cl.shift()).abs(),(lo-cl.shift()).abs()],axis=1).max(axis=1)
    df['atr']=tr.ewm(alpha=1/ATR_N,adjust=False,min_periods=ATR_N).mean()
    df['don_hi']=hi.rolling(LOOKBACK).max().shift(1)
    df['don_lo']=lo.rolling(LOOKBACK).min().shift(1)
    df['brk_up']=cl>df['don_hi']; df['brk_dn']=cl<df['don_lo']
    df['brk_str']=np.where(df['brk_up'],(cl-df['don_hi'])/df['atr'],
                  np.where(df['brk_dn'],(df['don_lo']-cl)/df['atr'],np.nan))
    # 壓縮指標：ATR 相對自身 96 根（8 小時）的百分位
    df['atr_pct_rank']=df['atr'].rolling(96).apply(lambda x:(x[-1]<=x).mean()*100, raw=True)
    # 布林帶寬百分位（squeeze 代理）
    ma=cl.rolling(20).mean(); sd=cl.rolling(20).std()
    bw=(4*sd)/ma
    df['bw']=bw
    df['bw_rank']=bw.rolling(96).apply(lambda x:(x[-1]<=x).mean()*100, raw=True)
    # 成交量相對水位
    df['vol_ma']=df['volume'].rolling(96).mean()
    df['vol_ratio']=df['volume']/df['vol_ma']
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
                       'gross':d*(ex-entry)/entry*100,'dir':d,'bars':ei-e})
        busy=ei
    return pd.DataFrame(trades)

ASSETS=[('BTC','/root/gridlab/btc_1m.parquet'),
        ('APT','/root/gridlab/apt_1m.parquet'),
        ('SUI','/root/gridlab/sui_1m.parquet'),
        ('FIL','/root/gridlab/fil_1m.parquet'),
        ('BCH','/root/gridlab/bch_1m.parquet')]

print("=== A. 多標的 5m 突破掃描（stop 2 / target 4, 48根最長持倉）===\n")
print(f"{'標的':>5}{'5m根數':>10}{'訊號':>8}{'ATR%':>8}{'fee/ATR':>9}"
      f"{'零費率平均':>12}{'taker平均':>11}{'勝率':>8}")
print("-"*72)
store={}
for name,path in ASSETS:
    if not os.path.exists(path): print(f"{name:>5}  檔案不存在"); continue
    df=add_ind(load_5m(path))
    df=df.dropna(subset=['atr','don_hi','don_lo']).copy()
    if len(df)<5000: print(f"{name:>5}  資料不足"); continue
    sigs=sorted([(int(i),1) for i in np.where(df['brk_up'].values)[0]]+
                [(int(i),-1) for i in np.where(df['brk_dn'].values)[0]])
    T0=bt(df,sigs,2.0,4.0,0.0); T1=bt(df,sigs,2.0,4.0,FEE_TAKER)
    atr_pct=np.nanmedian(df['atr']/df['close'])*100
    fee_atr=(2*FEE_TAKER)/(np.nanmedian(df['atr']/df['close']))
    print(f"{name:>5}{len(df):>10,}{len(sigs):>8}{atr_pct:>7.3f}%{fee_atr*100:>8.1f}%"
          f"{T0['gross'].mean() if len(T0) else 0:>+12.4f}"
          f"{T1['pnl'].mean() if len(T1) else 0:>+11.4f}"
          f"{(T1['pnl']>0).mean() if len(T1) else 0:>8.1%}")
    store[name]=(df,sigs,T0,T1)

print("\n=== B. 壓縮後突破（bw_rank < 30 = 波動收縮 → 突破）===\n")
print(f"{'標的':>5}{'壓縮突破訊號':>14}{'零費率平均':>12}{'taker平均':>11}{'勝率':>8}{'vs全收':>10}")
print("-"*64)
for name,(df,sigs,T0,T1) in store.items():
    m=df['bw_rank'].values<30
    sq=sorted([(int(i),1) for i in np.where(df['brk_up'].values & m)[0]]+
              [(int(i),-1) for i in np.where(df['brk_dn'].values & m)[0]])
    if len(sq)<200: print(f"{name:>5}  樣本不足({len(sq)})"); continue
    T0s=bt(df,sq,2.0,4.0,0.0); T1s=bt(df,sq,2.0,4.0,FEE_TAKER)
    delta=T0s['gross'].mean()-T0['gross'].mean()
    print(f"{name:>5}{len(sq):>14}{T0s['gross'].mean():>+12.4f}{T1s['pnl'].mean():>+11.4f}"
          f"{(T1s['pnl']>0).mean():>8.1%}{delta:>+10.4f}")

print("\n=== C. 壓縮 + 量能確認（bw_rank<30 且 vol_ratio>1.5）===\n")
print(f"{'標的':>5}{'訊號':>8}{'零費率平均':>12}{'taker平均':>11}{'勝率':>8}")
print("-"*48)
for name,(df,sigs,T0,T1) in store.items():
    m=(df['bw_rank'].values<30)&(df['vol_ratio'].values>1.5)
    sq=sorted([(int(i),1) for i in np.where(np.nan_to_num(df['brk_up'].values.astype(float))>0)[0] if m[i]]+
              [(int(i),-1) for i in np.where(np.nan_to_num(df['brk_dn'].values.astype(float))>0)[0] if m[i]])
    if len(sq)<150: print(f"{name:>5}  樣本不足({len(sq)})"); continue
    T0s=bt(df,sq,2.0,4.0,0.0); T1s=bt(df,sq,2.0,4.0,FEE_TAKER)
    print(f"{name:>5}{len(sq):>8}{T0s['gross'].mean():>+12.4f}{T1s['pnl'].mean():>+11.4f}"
          f"{(T1s['pnl']>0).mean():>8.1%}")

print("\n=== 判讀 ===")
print("零費率平均 > 0 且 taker 平均 > -0.02% → 該標的值得動用 Jev")
print("全部為負 → 5m 突破在這些標的上都沒有可開發空間")
