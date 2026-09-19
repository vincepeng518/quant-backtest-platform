#!/usr/bin/env python3
"""Stage 3: 用真實 grid_core 做 30 天分段回測，建立有依據的真值。

為什麼：docstring 的代理回歸 (PnL = 773 - 0.337*|位移| + 0.00081*路徑長)
重現不出來。改用真正的撮合引擎跑，真值是實際 PnL。

架構：
  1. 從 1m 資料取每個 30 天視窗（步長 5 天，重疊）
  2. 對每個視窗，在起點算指標（模擬「當下的資訊」）
  3. 用 grid_core 跑真實網格回測 → 真 PnL
  4. 後續：把指標餵 Jev，看它能不能預測 PnL 正負
"""
import sys, numpy as np, pandas as pd
sys.path.insert(0,'/root/Crypto-Backtesting-Lab')
from engine.grid_core import GridState

m = pd.read_parquet('/root/gridlab/btc_1m.parquet')
m.columns=[c.lower() for c in m.columns]
dc=[c for c in m.columns if c in ('dt','timestamp','time','date')][0]
m[dc]=pd.to_datetime(m[dc]); m=m.sort_values(dc).reset_index(drop=True)
m=m.rename(columns={'dt':'dt'})
print(f"1m 資料: {len(m):,} 根  {m[dc].min()} ~ {m[dc].max()}")

# 日線聚合（算指標用）
day = m.set_index(dc).resample('1D').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()
print(f"日線聚合: {len(day)} 根")

hi,lo,cl=day['high'],day['low'],day['close']
tr=pd.concat([(hi-lo),(hi-cl.shift()).abs(),(lo-cl.shift()).abs()],axis=1).max(axis=1)
day['atr']=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
day['natr']=day['atr']/day['close']
up=hi.diff(); dn=lo.diff().mul(-1)
pdm=up.clip(lower=0).where(up>dn,0.0); mdm=dn.clip(lower=0).where(dn>up,0.0)
pdi=100*pdm.ewm(alpha=1/14,adjust=False,min_periods=14).mean()/day['atr']
mdi=100*mdm.ewm(alpha=1/14,adjust=False,min_periods=14).mean()/day['atr']
dx=100*(pdi-mdi).abs()/(pdi+mdi).replace(0,1e-9)
day['adx']=dx.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
day['plus_di']=pdi; day['minus_di']=mdi
day['natr_thr']=day['natr'].expanding(60).quantile(0.5).shift(1)
day['sma50']=day['close'].rolling(50).mean(); day['sma200']=day['close'].rolling(200).mean()
day=day.reset_index().rename(columns={dc:'dt'})
print(f"指標就緒，有效 nATR 門檻: {day['natr_thr'].notna().sum()} 根")

# ── 真實網格回測：一個 30 天視窗 ──
M = m.set_index(dc)
def grid_pnl(start_ts, days=30, hr_mult=16.0, n_grids=80, qty=0.0023):
    """用 GridState 逐分鐘跑真實網格，回傳 PnL。"""
    end = start_ts + pd.Timedelta(days=days)
    seg = M.loc[(M.index>=start_ts)&(M.index<end)]
    if len(seg) < 1000: return None
    o=seg['open'].values.astype(float); h=seg['high'].values.astype(float)
    l=seg['low'].values.astype(float); c=seg['close'].values.astype(float)
    # half_range 用視窗起點的日線 ATR x 16（決策當下可知）
    i0 = day.index[day['dt']<=start_ts]
    if len(i0)==0: return None
    row = day.loc[i0[-1]]
    if pd.isna(row['atr']): return None
    hr = float(row['atr'])*hr_mult
    g = GridState(n_grids=n_grids, qty=qty, fee_bps=1.0, taker_bps=3.0,
                  recenter_gap=hr/3.0, cap_btc=0.20)
    g.build(o[0], hr)
    for i in range(len(c)):
        g.on_bar(o[i],h[i],l[i],c[i])
        g.settle(c[i], funding_rate_8h=0.0, minutes=1.0, next_half_range=hr)
    return {'pnl': g.equity(c[-1]), 'hr': hr, 'n_bars': len(seg)}

# ── 建立視窗樣本 ──
print("\n=== 建立 30 天視窗（步長 5 天）===")
t0 = day['dt'].iloc[250]
t_end = day['dt'].iloc[-1] - pd.Timedelta(days=31)
wins=[]
ts = t0
while ts <= t_end:
    i0 = day.index[day['dt']<=ts]
    if len(i0):
        r = day.loc[i0[-1]]
        if not pd.isna(r['natr_thr']) and not pd.isna(r['adx']):
            wins.append(ts)
    ts += pd.Timedelta(days=5)
print(f"候選視窗: {len(wins)} 個，開始真實回測…", flush=True)

rows=[]
for j,t in enumerate(wins):
    res=grid_pnl(t)
    if res is None: continue
    i0=day.index[day['dt']<=t]; r=day.loc[i0[-1]]
    seg=M.loc[(M.index>=t)&(M.index<t+pd.Timedelta(days=30))]['close']
    disp=abs(seg.iloc[-1]-seg.iloc[0])/seg.iloc[0]*100 if len(seg)>1 else None
    rows.append({'start':t,'close':float(r['close']),'natr':float(r['natr']),
                 'natr_thr':float(r['natr_thr']),'adx':float(r['adx']),
                 'plus_di':float(r['plus_di']),'minus_di':float(r['minus_di']),
                 'atr':float(r['atr']),'sma50':float(r['sma50']),'sma200':float(r['sma200']),
                 'pnl':res['pnl'],'hr':res['hr'],'fwd_disp_pct':disp})
    if (j+1)%20==0: print(f"  {j+1}/{len(wins)}…", flush=True)

S=pd.DataFrame(rows)
S.to_csv('/tmp/grid_real_windows.csv',index=False)
print(f"\n完成 {len(S)} 個視窗 → /tmp/grid_real_windows.csv")
print(f"\n=== 真實 PnL 分布 ===")
print(S['pnl'].describe().to_string())
print(f"PnL > 0 比例: {(S['pnl']>0).mean():.1%}")
print(f"\n規則 gate 過（natr>=thr）的視窗: {(S['natr']>=S['natr_thr']).sum()} / {len(S)}")
print(f"  其中 PnL>0: {(S[S['natr']>=S['natr_thr']]['pnl']>0).mean():.1%}")
print(f"規則 gate 不過（flat）的視窗: {(S['natr']<S['natr_thr']).sum()}")
print(f"  其中 PnL>0: {(S[S['natr']<S['natr_thr']]['pnl']>0).mean():.1%}")
