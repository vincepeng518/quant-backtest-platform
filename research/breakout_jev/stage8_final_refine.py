#!/usr/bin/env python3
"""Stage 8（最終）: 長回看突破的規則層精煉 + Jev 的最後一次機會。

Stage 6-7 結論：
  - 長回看（288/576 根）是唯一有 gross edge 的維度
    BTC LB576 +0.0369%, BTC LB288 +0.0194%, FIL LB288 +0.0539%（全期總）
  - Jev 過濾無效：準確率 49-52% vs 基準 50-54%，全數未勝過基準

本檔檢驗兩件事：
  1. 規則層能否精煉（用 ATR 位置、突破幅度、動能狀態切分）
     → 若規則就能篩出正期望子集，Jev 完全不需要
  2. Jev 是否有任何子集有效（信心分層 × 過濾方向反轉）
     → 最後一次機會，用多幣種合併樣本提高統計力
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
CACHE='/root/Crypto-Backtesting-Lab/runtime/breakout_jev_final_cache.json'
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
    df['range_pos']=(cl-df['don_lo'])/(df['don_hi']-df['don_lo']).replace(0,np.nan)
    df['ret_48']=cl.pct_change(48)*100
    df['ret_288']=cl.pct_change(min(lb,288))*100
    return df

def gen_trades(df, stop_atr=2.0, target_atr=4.0):
    n=len(df); o=df['open'].values; h=df['high'].values; l=df['low'].values
    c=df['close'].values; atr=df['atr'].values
    up=np.where(df['brk_up'].values)[0]; dn=np.where(df['brk_dn'].values)[0]
    sigs=sorted([(int(i),1) for i in up]+[(int(i),-1) for i in dn])
    rows=[]; busy=-1
    for idx,d in sigs:
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
        r=df.iloc[idx]
        rows.append({'asset':ASSET,'lb':LB,'idx':idx,'dir':d,'gross':d*(ex-entry)/entry*100,
                     'close':float(r['close']),'atr':float(a),
                     'brk_str':float(r['brk_str']) if not pd.isna(r['brk_str']) else 0.0,
                     'range_pos':float(r['range_pos']) if not pd.isna(r['range_pos']) else np.nan,
                     'ret_48':float(r['ret_48']) if not pd.isna(r['ret_48']) else np.nan,
                     'ret_288':float(r['ret_288']) if not pd.isna(r['ret_288']) else np.nan,
                     'bars_held':ei-e})
        busy=ei
    return pd.DataFrame(rows)

ASSETS_ALL=[('BTC','/root/gridlab/btc_1m.parquet'),('APT','/root/gridlab/apt_1m.parquet'),
            ('SUI','/root/gridlab/sui_1m.parquet'),('FIL','/root/gridlab/fil_1m.parquet'),
            ('BCH','/root/gridlab/bch_1m.parquet')]
CONFIGS=[(A,P,LB) for A,P in ASSETS_ALL for LB in [288,576]]

print("=== 1. 規則層精煉（長回看全組合，零費率）===\n")
allT=[]
for ASSET,PATH,LB in CONFIGS:
    if not os.path.exists(PATH): continue
    df=add_ind(load_5m(PATH),LB).dropna(subset=['atr','don_hi','don_lo'])
    if len(df)<3000: continue
    T=gen_trades(df)
    if len(T)<100: continue
    allT.append(T)
    print(f"{ASSET} LB{LB}: n={len(T):>5}  平均 {T['gross'].mean():+.4f}%  "
          f"總 {T['gross'].sum():>+8.1f}%  勝率 {(T['gross']>0).mean():.1%}")
ALL=pd.concat(allT, ignore_index=True)
print(f"\n合併 {len(ALL)} 筆  平均 {ALL['gross'].mean():+.4f}%")

print("\n=== 2. 突破幅度分層（找有沒有可篩維度）===")
q=ALL['brk_str'].quantile([0,0.25,0.5,0.75,1.0]).values
for i in range(4):
    m=(ALL['brk_str']>=q[i])&(ALL['brk_str']<=q[i+1])
    s=ALL[m]
    if len(s)<50: continue
    print(f"  brk_str {q[i]:.2f}-{q[i+1]:.2f}: n={len(s):>5}  平均 {s['gross'].mean():+.4f}%  "
          f"勝率 {(s['gross']>0).mean():.1f}%")

print("\n=== 3. 動能狀態分層（突破前的走勢）===")
for col,qs in [('ret_48',[0.25,0.75]),('ret_288',[0.25,0.75])]:
    v=ALL[col].dropna()
    if len(v)<100: continue
    lo,hi=v.quantile(qs)
    sub=ALL[ALL[col].notna()]
    for lbl,m in [('低（前段下跌）',sub[col]<=lo),('高（前段上漲）',sub[col]>=hi)]:
        s=sub[m]
        print(f"  {col} {lbl}: n={len(s):>5}  平均 {s['gross'].mean():+.4f}%  "
              f"勝率 {(s['gross']>0).mean():.1f}%")

print("\n=== 4. 按標的（找是否集中）===\n")
for a,g in ALL.groupby('asset'):
    print(f"  {a:>4}: n={len(g):>5}  平均 {g['gross'].mean():+.4f}%  總 {g['gross'].sum():>+8.1f}%")

print("\n=== 5. 費率後（合併, maker 0.02% / taker 0.05%）===")
for fee,lbl in [(0.0002,'maker 0.02%'),(0.0005,'taker 0.05%')]:
    net=ALL['gross'].mean()-2*fee*100
    print(f"  {lbl}: 平均淨 {net:+.4f}%  → {'正期望 ✓' if net>0 else '負期望 ✗'}")

print("\n=== 6. Jev 最後一次機會（合併多標的，提高統計力）===\n")
def jev_call(rec):
    key=f"{rec['asset']}_{rec['lb']}_{rec['idx']}"
    if os.path.exists(CACHE):
        try:
            c=json.load(open(CACHE))
        except Exception: c={}
    else: c={}
    if key in c: return c[key]
    d=rec['dir']
    state={"asset":rec['asset'],"timeframe":"5 minute","current_close":round(rec['close'],6),
      "atr_14":round(rec['atr'],6),"atr_as_pct_of_price":round(rec['atr']/rec['close']*100,3),
      "lookback_bars":rec['lb'],
      f"price_broke_above_{rec['lb']}bar_high":bool(d>0),
      f"price_broke_below_{rec['lb']}bar_low":bool(d<0),
      "breakout_distance_in_atr":round(rec['brk_str'],3),
      "position_within_lookback_range":None if pd.isna(rec['range_pos']) else round(rec['range_pos'],3),
      "recent_48bar_return_pct":None if pd.isna(rec['ret_48']) else round(rec['ret_48'],2)}
    body=json.dumps({"state":state,"questions":{
      "res":{"type":"choice","instructions":
        f"價格剛突破 {rec['lb']} 根 5 分鐘 K 線的{'高點' if d>0 else '低點'}。"
        f"接下來 {MAX_HOLD} 根內，先同向再走 2 ATR，還是先反向 2 ATR？",
        "criteria":{"continue_further":"先同向","reverse_back":"先反向"}},
      "conf":{"type":"score","instructions":"把握程度",
        "criteria":["幾乎沒把握","略有把握","中等把握","很有把握","極有把握"]}}}).encode()
    for att in range(3):
        try:
            req=urllib.request.Request(GATEWAY,data=body,headers=HDR,method='POST')
            with urllib.request.urlopen(req,timeout=60) as r:
                dd=json.loads(r.read())
            A=dd['answers']
            res={'choice':A['res']['choice'],'conf':float(A['conf']['score']),
                 'p_cont':float(A['res']['probabilities'].get('continue_further',0)),
                 'tok':dd.get('usage',{}).get('inputTokens',0)}
            c=CACHE_SAFE_LOAD(); c[key]=res; CACHE_SAFE_SAVE(c); return res
        except Exception:
            time.sleep(2*(att+1))
    return {'choice':'ERR','conf':None,'p_cont':None,'tok':0}

import threading
_LK=threading.Lock()
def CACHE_SAFE_LOAD():
    with _LK:
        try:
            with open(CACHE) as f: t=f.read().strip()
            return json.loads(t) if t else {}
        except Exception: return {}
def CACHE_SAFE_SAVE(c):
    with _LK:
        with open(CACHE+'.tmp','w') as f: json.dump(c,f)
        os.replace(CACHE+'.tmp',CACHE)

rng=np.random.default_rng(99)
samp=ALL.sample(n=min(600,len(ALL)), random_state=99).reset_index(drop=True)
print(f"抽樣 {len(samp)} 筆（多標的合併）…", flush=True)
t0=time.perf_counter()
with ThreadPoolExecutor(max_workers=6) as ex:
    res=list(ex.map(jev_call, [r for _,r in samp.iterrows()]))
print(f"完成 {len(res)} 筆，{time.perf_counter()-t0:.0f}s")

samp['jev_cont']=[x['choice']=='continue_further' for x in res]
samp['jev_conf']=[x['conf'] for x in res]
tok=sum(x.get('tok',0) for x in res)
print(f"token {tok} = ${tok/1e6*0.042:.5f}")
print(f"Jev 答 continue 比例: {samp['jev_cont'].mean():.1%}")

# Jev 過濾效果（每筆平均，公平比較）
print(f"\n  全收           : 平均 {samp['gross'].mean():+.4f}%  n={len(samp)}")
k=samp[samp['jev_cont']]
print(f"  Jev 保留 continue: 平均 {k['gross'].mean():+.4f}%  n={len(k)}")
r=samp[~samp['jev_cont']]
print(f"  Jev 保留 reverse : 平均 {r['gross'].mean():+.4f}%  n={len(r)}")
print(f"  → Jev 選擇的方向: "
      f"{'有效（保留的較好）' if k['gross'].mean()>samp['gross'].mean() else '無效（保留的沒較好）'}")

print(f"\n=== 信心分層 ===")
for lo,hi in [(0,1.5),(1.5,2.5),(2.5,3.5),(3.5,5)]:
    s=samp[(samp['jev_conf']>=lo)&(samp['jev_conf']<hi)]
    if len(s)<20: continue
    print(f"  信心 {lo}-{hi}: n={len(s):>3}  零費平均 {s['gross'].mean():+.4f}%  "
          f"maker平均 {s['gross'].mean()-0.04:+.4f}%")

samp.to_csv('/tmp/breakout_final_jev.csv',index=False)
print("\n已存 /tmp/breakout_final_jev.csv")
