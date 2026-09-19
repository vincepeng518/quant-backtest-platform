#!/usr/bin/env python3
"""Stage 7（決定性）: 長回看突破 + 費率分層 + Jev 過濾。

Stage 6 首次發現正 gross edge:
    FIL LB=288  n=664   +0.0539%
    BTC LB=576  n=1489  +0.0369%
    BTC LB=288  n=2236  +0.0194%

這些能否實用取決於 (a) 費率、(b) Jev 能否把弱 edge 放大。
本檔直接回答：Jev 過濾後的淨期望值 vs 規則全收。

設計（沿用已驗證的方法論）：
  1. 樣本隨機分散（非窄帶）
  2. 中性提問、零引導
  3. 基準線對照（多數類）
  4. 費率分層（taker 0.05% / maker 0.02% / VIP 0.01%）
"""
import sys, os, os, json, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,'/root/Crypto-Backtesting-Lab')
import numpy as np, pandas as pd

API_KEY=os.getenv("AI_GATEWAY_API_KEY") or \
  os.environ.get("AI_GATEWAY_API_KEY", "")
GATEWAY="https://ai-gateway.vercel.sh/v4/ai/evaluation-model"
HDR={'Authorization':f'Bearer {API_KEY}','Content-Type':'application/json',
     'ai-gateway-protocol-version':'0.0.1','ai-evaluation-model-specification-version':'4',
     'ai-model-id':'typesafe-ai/jev'}
CACHE='/root/Crypto-Backtesting-Lab/runtime/breakout_jev_lb_cache.json'
TF='5min'; ATR_N=14; MAX_HOLD=48; LEG=2.0

def load_5m(path):
    M=pd.read_parquet(path)
    dc=[c for c in M.columns if c.lower() in ('dt','timestamp','time','date')][0]
    M[dc]=pd.to_datetime(M[dc]); M=M.sort_values(dc).set_index(dc)
    out=M.resample(TF).agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()
    return out

def add_ind(df,lb):
    df=df.copy(); hi,lo,cl=df['high'],df['low'],df['close']
    tr=pd.concat([(hi-lo),(hi-cl.shift()).abs(),(lo-cl.shift()).abs()],axis=1).max(axis=1)
    df['atr']=tr.ewm(alpha=1/ATR_N,adjust=False,min_periods=ATR_N).mean()
    df['don_hi']=hi.rolling(lb).max().shift(1); df['don_lo']=lo.rolling(lb).min().shift(1)
    df['brk_up']=cl>df['don_hi']; df['brk_dn']=cl<df['don_lo']
    df['brk_str']=np.where(df['brk_up'],(cl-df['don_hi'])/df['atr'],
                  np.where(df['brk_dn'],(df['don_lo']-cl)/df['atr'],np.nan))
    df['ret_12']=cl.pct_change(12)*100; df['ret_48']=cl.pct_change(48)*100
    return df

def run_trades(df, signals, fee, stop_atr=2.0, target_atr=4.0):
    n=len(df)
    o=df['open'].values; h=df['high'].values; l=df['low'].values; c=df['close'].values
    atr=df['atr'].values
    out=[]; busy=-1
    for idx,d in signals:
        if idx<=busy or idx+1>=n or np.isnan(atr[idx]): continue
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
        out.append({'idx':idx,'dir':d,'gross':d*(ex-entry)/entry*100,
                    'pnl':d*(ex-entry)/entry*100-2*fee*100})
        busy=ei
    return pd.DataFrame(out)

import threading
_CACHE_LOCK = threading.Lock()

def _load_cache():
    with _CACHE_LOCK:
        if not os.path.exists(CACHE):
            return {}
        try:
            with open(CACHE) as f:
                txt = f.read().strip()
            return json.loads(txt) if txt else {}
        except (json.JSONDecodeError, OSError):
            # 損壞的快取直接重建，不讓它中斷實驗
            return {}

def _save_cache(c):
    with _CACHE_LOCK:
        tmp = CACHE + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(c, f)
        os.replace(tmp, CACHE)

def jev_filter(rec):
    key=f"{rec['asset']}_{rec['lb']}_{rec['idx']}"
    cache=_load_cache()
    if key in cache: return cache[key]
    d=rec['dir']
    state={"asset":rec['asset'],"timeframe":"5 minute",
      "current_close":round(rec['close'],4),
      "atr_14":round(rec['atr'],6),
      "atr_as_pct_of_price":round(rec['atr']/rec['close']*100,3),
      f"price_broke_above_{rec['lb']}bar_high":bool(d>0),
      f"price_broke_below_{rec['lb']}bar_low":bool(d<0),
      "lookback_bars":rec['lb'],
      "breakout_distance_in_atr":round(rec['brk_str'],3),
      "recent_12bar_return_pct":None if pd.isna(rec['ret_12']) else round(rec['ret_12'],2),
      "recent_48bar_return_pct":None if pd.isna(rec['ret_48']) else round(rec['ret_48'],2)}
    body=json.dumps({"state":state,"questions":{
      "res":{"type":"choice",
        "instructions":(f"價格剛突破 {rec['lb']} 根 5 分鐘 K 線的"
                        f"{'高點' if d>0 else '低點'}。接下來 {MAX_HOLD} 根內，"
                        f"哪個先被觸及：同向再走 {LEG} ATR，還是反向走 {LEG} ATR？"),
        "criteria":{"continue_further":f"先同向 {LEG} ATR","reverse_back":f"先反向 {LEG} ATR"}},
      "conf":{"type":"score","instructions":"把握程度",
        "criteria":["幾乎沒把握","略有把握","中等把握","很有把握","極有把握"]}}}).encode()
    last=None
    for att in range(3):
        try:
            req=urllib.request.Request(GATEWAY,data=body,headers=HDR,method='POST')
            with urllib.request.urlopen(req,timeout=60) as r:
                dd=json.loads(r.read())
            A=dd['answers']; pr=A['res']['probabilities']
            res={'choice':A['res']['choice'],'p_cont':float(pr.get('continue_further',0)),
                 'conf':float(A['conf']['score']),
                 'tok':dd.get('usage',{}).get('inputTokens',0)}
            c=_load_cache(); c[key]=res; _save_cache(c); return res
        except Exception as ex:
            last=ex; time.sleep(2*(att+1))
    return {'choice':'ERR','p_cont':None,'conf':None,'tok':0}

# ── 主流程：BTC LB=288, BTC LB=576, FIL LB=288 ──
CONFIGS=[('BTC','/root/gridlab/btc_1m.parquet',288),
         ('BTC','/root/gridlab/btc_1m.parquet',576),
         ('FIL','/root/gridlab/fil_1m.parquet',288)]
NSAMPLE=200

print("=== 1. 費率分層（長回看，規則全收）===\n")
print(f"{'組合':>18}{'n':>7}{'gross':>10}"
      f"{'taker.05':>11}{'maker.02':>11}{'VIP.01':>10}{'零費':>9}")
print("-"*76)
store={}
for asset,path,lb in CONFIGS:
    df=add_ind(load_5m(path),lb).dropna(subset=['atr','don_hi','don_lo'])
    sigs=sorted([(int(i),1) for i in np.where(df['brk_up'].values)[0]]+
                [(int(i),-1) for i in np.where(df['brk_dn'].values)[0]])
    T0=run_trades(df,sigs,0.0)
    T1=run_trades(df,sigs,0.0005); T2=run_trades(df,sigs,0.0002); T3=run_trades(df,sigs,0.0001)
    lbl=f"{asset} LB{lb}"
    print(f"{lbl:>18}{len(T0):>7}{T0['gross'].mean():>+10.4f}"
          f"{T1['pnl'].mean():>+11.4f}{T2['pnl'].mean():>+11.4f}"
          f"{T3['pnl'].mean():>+10.4f}{T0['gross'].mean():>+9.4f}")
    store[(asset,lb)]=(df,sigs,T0)

# ── 2. Jev 過濾（對最優組合）──
print(f"\n=== 2. Jev 過濾測試（每組隨機抽 {NSAMPLE} 訊號）===\n")
rng=np.random.default_rng(2026)
for asset,path,lb in CONFIGS:
    df,sigs,T0=store[(asset,lb)]
    if len(sigs)<NSAMPLE: continue
    pick=rng.choice(len(sigs),size=NSAMPLE,replace=False)
    sample=[sigs[i] for i in sorted(pick)]
    rows=[]
    for i,d in sample:
        r=df.iloc[i]
        rows.append({'asset':asset,'lb':lb,'idx':i,'dir':d,'close':float(r['close']),
                     'atr':float(r['atr']),'brk_str':float(r['brk_str']) if not pd.isna(r['brk_str']) else 0,
                     'ret_12':r['ret_12'],'ret_48':r['ret_48']})
    t0=time.perf_counter()
    with ThreadPoolExecutor(max_workers=6) as ex:
        res=list(ex.map(jev_filter, rows))
    el=time.perf_counter()-t0
    tok=sum(x.get('tok',0) for x in res)
    print(f"{asset} LB{lb}: {len(res)} 筆 {el:.0f}s，{tok} token = ${tok/1e6*0.042:.5f}")
    print(f"  Jev 答 continue: {sum(1 for x in res if x['choice']=='continue_further')}/{len(res)} "
          f"({sum(1 for x in res if x['choice']=='continue_further')/len(res):.1%})")

    # 真值與對照
    tr={}
    o=df['open'].values; h=df['high'].values; l=df['low'].values; c=df['close'].values
    atr=df['atr'].values; n=len(df)
    for i,d in sample:
        e=i+1
        if e>=n or np.isnan(atr[i]): continue
        a=atr[i]; entry=o[e]
        tgt=entry+d*LEG*a; inv=entry-d*LEG*a
        first=None
        for j in range(e,min(e+MAX_HOLD,n)):
            ht=(h[j]>=tgt) if d>0 else (l[j]<=tgt)
            hi=(l[j]<=inv) if d>0 else (h[j]>=inv)
            if ht and hi: first='both'; break
            if ht: first='cont'; break
            if hi: first='fail'; break
        tr[(i,d)]=first or 'none'
    ok=[(r,tr[(r['idx'],r['dir'])]) for r,x in zip(rows,res) if tr.get((r['idx'],r['dir'])) in ('cont','fail')]
    if not ok:
        print("  無有效樣本\n"); continue
    jev_c=[x['choice']=='continue_further' for _,x in zip(rows,res) if tr.get((_['idx'],_['dir'])) in ('cont','fail')]
    truth=[t=='cont' for _,t in ok]
    acc=np.mean([a==b for a,b in zip(jev_c,truth)])
    base=max(np.mean(truth), 1-np.mean(truth))
    print(f"  有效 {len(ok)} 筆 | Jev 準確率 {acc:.1%} | 基準線 {base:.1%} | "
          f"{'✓勝過基準' if acc>base+0.02 else '✗未勝過基準'}")

    # 用 Jev 過濾後的交易淨值
    keep={r['idx'] for r,x in zip(rows,res) if x['choice']=='ERR' or x['choice']=='continue_further'}
    fsigs=[(i,d) for i,d in sigs if i in keep]
    for fee,fl in [(0.0,'零費'),(0.0002,'maker.02')]:
        Tall=run_trades(df,sigs,fee); Tfil=run_trades(df,fsigs,fee)
        print(f"  {fl}: 全收 {len(Tall)}筆 {Tall['pnl'].sum():+8.1f}% → "
              f"Jev過濾 {len(Tfil)}筆 {Tfil['pnl'].sum():+8.1f}%  "
              f"({'改善' if Tfil['pnl'].sum()>Tall['pnl'].sum() else '惡化'})")
    print()
