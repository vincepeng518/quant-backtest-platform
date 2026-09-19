#!/usr/bin/env python3
"""Stage 9（收斂）: 整合三條件 + 統計顯著性檢定。

Stage 6-8 已定位 edge 在:
  - 長回看（288/576 根）
  - 特定標的（BTC, FIL）
  - 小突破（brk_str 最低四分位 +0.0410%）

本檔檢驗三個條件疊加後能否翻正，並用 bootstrap 檢定是否顯著
（n 小，必須排除運氣）。

同時測「maker 進場」情境：突破策略可在關卡價掛限價單 → 進場是 maker
（費用減半），這是實務上可行且尚未評估的假設。
"""
import sys, os
sys.path.insert(0,'/root/Crypto-Backtesting-Lab')
import numpy as np, pandas as pd

TF='5min'; ATR_N=14; MAX_HOLD=48

def load_5m(p):
    M=pd.read_parquet(p)
    dc=[x for x in M.columns if x.lower() in ('dt','timestamp','time','date')][0]
    M[dc]=pd.to_datetime(M[dc]); M=M.sort_values(dc).set_index(dc)
    return M.resample(TF).agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()

def add_ind(df,lb):
    df=df.copy(); hi,lo,cl=df['high'],df['low'],df['close']
    tr=pd.concat([(hi-lo),(hi-cl.shift()).abs(),(lo-cl.shift()).abs()],axis=1).max(axis=1)
    df['atr']=tr.ewm(alpha=1/ATR_N,adjust=False,min_periods=ATR_N).mean()
    df['don_hi']=hi.rolling(lb).max().shift(1); df['don_lo']=lo.rolling(lb).min().shift(1)
    df['brk_up']=cl>df['don_hi']; df['brk_dn']=cl<df['don_lo']
    df['brk_str']=np.where(df['brk_up'],(cl-df['don_hi'])/df['atr'],
                  np.where(df['brk_dn'],(df['don_lo']-cl)/df['atr'],np.nan))
    return df

def trades(df, stop_atr=2.0, target_atr=4.0, brk_max=None):
    n=len(df); o=df['open'].values; h=df['high'].values; l=df['low'].values
    c=df['close'].values; atr=df['atr'].values; bs=df['brk_str'].values
    up=np.where(df['brk_up'].values)[0]; dn=np.where(df['brk_dn'].values)[0]
    sigs=sorted([(int(i),1) for i in up]+[(int(i),-1) for i in dn])
    rows=[]; busy=-1
    for idx,d in sigs:
        if idx<=busy or idx+1>=n or np.isnan(atr[idx]): continue
        if brk_max is not None and (np.isnan(bs[idx]) or bs[idx]>brk_max): continue
        e=idx+1; entry=o[e]; a=atr[idx]
        if a<=0 or entry<=0: continue
        stop=entry-d*stop_atr*a; tgt=entry+d*target_atr*a
        ex=None; ei=None
        for j in range(e,min(e+MAX_HOLD,n)):
            if d>0:
                if l[j]<=stop: ex,ei=stop,j; break
                if h[j]>=tgt:  ex,ei=tgt,j; break
            else:
                if h[j]>=stop: ex,ei=stop,j; break
                if l[j]<=tgt:  ex,ei=tgt,j; break
        if ex is None: ei=min(e+MAX_HOLD-1,n-1); ex=c[ei]
        rows.append({'gross':d*(ex-entry)/entry*100,'dir':d,'idx':idx})
        busy=ei
    return pd.DataFrame(rows)

def bootstrap_ci(x, n=10000, seed=7):
    """回傳 (mean, lo95, hi95) 的 bootstrap 信賴區間"""
    if len(x)<5: return (np.nan,np.nan,np.nan)
    rng=np.random.default_rng(seed)
    m=np.array([rng.choice(x,size=len(x),replace=True).mean() for _ in range(n)])
    return (float(np.mean(x)), float(np.percentile(m,2.5)), float(np.percentile(m,97.5)))

print("=== 1. 三條件整合：BTC/FIL + 長回看 + 小突破 ===\n")
print("小突破門檻用全樣本第 25 百分位 = 0.28 ATR（Stage 8 發現）\n")
print(f"{'配置':>24}{'n':>6}{'零費平均':>11}{'95% CI':>22}{'顯著?':>8}")
print("-"*74)
results={}
for asset,path,lbs in [('BTC','/root/gridlab/btc_1m.parquet',[288,576]),
                       ('FIL','/root/gridlab/fil_1m.parquet',[288,576])]:
    if not os.path.exists(path): continue
    raw=load_5m(path)
    for lb in lbs:
        df=add_ind(raw,lb).dropna(subset=['atr','don_hi','don_lo'])
        if len(df)<3000: continue
        for bmax,lbl in [(None,'全收'),(0.28,'小突破<0.28')]:
            T=trades(df,brk_max=bmax)
            if len(T)<30: continue
            g=T['gross'].values
            mean,lo,hi=bootstrap_ci(g)
            sig='是' if lo>0 else '否'
            print(f"{asset+' LB'+str(lb)+' '+lbl:>24}{len(T):>6}{mean:>+11.4f}"
                  f"{f'[{lo:+.4f}, {hi:+.4f}]':>22}{sig:>8}")
            results[(asset,lb,lbl)]=(mean,lo,hi,len(T))

print("\n=== 2. BTC LB576 小突破 詳細（最被看好的配置）===")
raw=load_5m('/root/gridlab/btc_1m.parquet')
df=add_ind(raw,576).dropna(subset=['atr','don_hi','don_lo'])
T=trades(df,brk_max=0.28)
print(f"n={len(T)}, 零費平均 {T['gross'].mean():+.4f}%, 勝率 {(T['gross']>0).mean():.1%}")

print("\n  各費率情境（含 maker 進場假設）:")
# taker 進 taker 出 / maker 進 taker 出 / 全 maker
scenarios=[
    ('全 taker (0.05%+0.05%)', 0.0010),
    ('maker進+taker出 (0.02%+0.05%)', 0.0007),
    ('maker進+maker出 (0.02%+0.02%)', 0.0004),
    ('VIP 全 (0.01%+0.01%)', 0.0002),
]
for lbl,cost in scenarios:
    net=T['gross'].mean()-cost*100
    # 用 bootstrap 檢定淨值
    netarr=T['gross'].values-cost*100
    _,lo,hi=bootstrap_ci(netarr)
    print(f"    {lbl:32s} 平均淨 {net:+.4f}%  95%CI [{lo:+.4f},{hi:+.4f}]  "
          f"{'顯著正 ✓' if lo>0 else '不顯著'}")

print("\n=== 3. 對照：擴大樣本（放寬小突破門檻）===")
for bmax in [0.28,0.4,0.6,None]:
    T=trades(df,brk_max=bmax)
    if len(T)<30: continue
    m,lo,hi=bootstrap_ci(T['gross'].values)
    print(f"  brk_max {str(bmax):>5}: n={len(T):>5}  零費 {m:+.4f}%  "
          f"CI [{lo:+.4f},{hi:+.4f}]  {'顯著 ✓' if lo>0 else ''}")

print("\n=== 4. 時間穩定性（切前後兩半）===")
T=trades(df,brk_max=0.28)
if len(T)>=60:
    h1=T.iloc[:len(T)//2]; h2=T.iloc[len(T)//2:]
    m1,l1,u1=bootstrap_ci(h1['gross'].values); m2,l2,u2=bootstrap_ci(h2['gross'].values)
    print(f"  前 1/2: n={len(h1):>4}  零費 {m1:+.4f}%  CI [{l1:+.4f},{u1:+.4f}]")
    print(f"  後 1/2: n={len(h2):>4}  零費 {m2:+.4f}%  CI [{l2:+.4f},{u2:+.4f}]")
    print(f"  → {'兩半皆正（穩定）' if m1>0 and m2>0 else '不穩定（一半為負）'}")

print("\n=== 5. 多空拆解 ===")
for d,lbl in [(1,'多'),(-1,'空')]:
    s=T[T['dir']==d]
    if len(s)<15: continue
    m,lo,hi=bootstrap_ci(s['gross'].values)
    print(f"  {lbl}: n={len(s):>4}  零費 {m:+.4f}%  CI [{lo:+.4f},{hi:+.4f}]")
