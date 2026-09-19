#!/usr/bin/env python3
"""Stage 4（決定性測試）: Jev 能不能預測 5m 突破的成敗？

前情（Stage 1-3 已證）：
  - 費用不是主因：零費率下平均僅 +0.0018%（≈0）
  - 所有參數化特徵與結果相關 ≈ 0:
      brk_atr +0.001, atr_pct -0.020, ret_1 -0.009, ret_12 -0.016, ret_48 -0.019
  → 規則能算的特徵全部無預測力。

但這正是 Jev 的價值主張所在：找出規則算不出的結構。
本測試直接檢驗：餵 Jev 中性 state，它能否預測突破會延續還是失敗。

設計（吸取前幾輪失敗教訓）：
  1. 樣本隨機分散全期（不取窄帶）→ 保證特徵變異
  2. 中性提問，零引導文字（不暗示答案）
  3. 原子標的：哪個先到 —— +2ATR 延續 or -2ATR 回撤
  4. 對照基準線：全猜多數類的準確率（若 Jev 贏不過基準 = 無技能）
"""
import sys, os, os, json, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,'/root/Crypto-Backtesting-Lab')
import numpy as np, pandas as pd

API_KEY = os.getenv("AI_GATEWAY_API_KEY") or \
    os.environ.get("AI_GATEWAY_API_KEY", "")
GATEWAY="https://ai-gateway.vercel.sh/v4/ai/evaluation-model"
HDR={'Authorization':f'Bearer {API_KEY}','Content-Type':'application/json',
     'ai-gateway-protocol-version':'0.0.1','ai-evaluation-model-specification-version':'4',
     'ai-model-id':'typesafe-ai/jev'}
CACHE='/root/Crypto-Backtesting-Lab/runtime/breakout_jev_cache.json'

df = pd.read_parquet('/tmp/btc_5m.parquet')
n=len(df)
o=df['open'].values; h=df['high'].values; l=df['low'].values; c=df['close'].values
atr=df['atr'].values
SAMPLE=250
LEG=2.0   # 2 ATR 為「到達」門檻
HORIZON=48

# ── 建立樣本 + 真值（哪個先到）──
up=np.where(df['brk_up'].values)[0]; dn=np.where(df['brk_dn'].values)[0]
all_sig=sorted([(int(i),1) for i in up]+[(int(i),-1) for i in dn])
rng=np.random.default_rng(2026)
pick=rng.choice(len(all_sig), size=min(SAMPLE,len(all_sig)), replace=False)
sample=[all_sig[i] for i in sorted(pick)]

rows=[]
for i,d in sample:
    if i+1>=n or np.isnan(atr[i]): continue
    e=i+1; entry=o[e]; a=atr[i]
    if a<=0 or entry<=0: continue
    target=entry+d*LEG*a; inval=entry-d*LEG*a
    first=None
    for j in range(e, min(e+HORIZON,n)):
        hit_t = (h[j]>=target) if d>0 else (l[j]<=target)
        hit_i = (l[j]<=inval)  if d>0 else (h[j]>=inval)
        if hit_t and hit_i: first='both'; break
        if hit_t: first='cont'; break
        if hit_i: first='fail'; break
    if first is None: first='none'
    rows.append({'i':i,'dir':d,'entry':entry,'atr':a,'first':first,
                 'close':c[i],'don_hi':df['don_hi'].values[i],'don_lo':df['don_lo'].values[i],
                 'ret_1':df['ret_1'].values[i],'ret_12':df['ret_12'].values[i],
                 'ret_48':df['ret_48'].values[i],
                 'brk_str':df['brk_strength_up'].values[i] if d>0 else df['brk_strength_dn'].values[i]})
S=pd.DataFrame(rows)
print(f"樣本 {len(S)} 個訊號（隨機分散全期）")
print(f"真值分布: {S['first'].value_counts().to_dict()}")
base_cont=(S['first']=='cont').mean()
print(f"基準線（全猜 cont）: {base_cont:.1%}")

# ── 問 Jev（中性、零引導）──
cache=json.load(open(CACHE)) if os.path.exists(CACHE) else {}

def jev_call(rec):
    key=f"{rec['i']}_{rec['dir']}"
    if key in cache: return cache[key]
    d=rec['dir']; a=rec['atr']
    # 中性 state：只給市場數據，不給任何結論性文字
    state={
      "asset":"BTC/USDT","timeframe":"5 minute","current_close":round(rec['close'],1),
      "atr_14":round(a,1),
      "atr_as_pct_of_price":round(a/rec['close']*100,3),
      "recent_1bar_return_pct":None if pd.isna(rec['ret_1']) else round(rec['ret_1'],3),
      "recent_12bar_return_pct":None if pd.isna(rec['ret_12']) else round(rec['ret_12'],2),
      "recent_48bar_return_pct":None if pd.isna(rec['ret_48']) else round(rec['ret_48'],2),
      "price_broke_above_24bar_high":bool(d>0),
      "price_broke_below_24bar_low":bool(d<0),
      "breakout_distance_in_atr":round(rec['brk_str'],3),
      "distance_to_24bar_high":round(rec['don_hi']-rec['close'],1),
      "distance_to_24bar_low":round(rec['close']-rec['don_lo'],1),
    }
    body=json.dumps({"state":state,"questions":{
      "first_touch":{"type":"choice",
        "instructions":(f"價格剛突破。接下來 {HORIZON} 根 5 分鐘 K 線內，"
                        f"哪個價位會先被觸及：繼續同方向走 {LEG} ATR，"
                        f"還是反向走 {LEG} ATR？"),
        "criteria":{"continue_further":f"先同向再走 {LEG} ATR",
                    "reverse_back":f"先反向走 {LEG} ATR"}},
      "conf":{"type":"score","instructions":"你對這個判斷的把握程度",
        "criteria":["幾乎沒把握","略有把握","中等把握","很有把握","極有把握"]}}}).encode()
    last=None
    for att in range(3):
        try:
            req=urllib.request.Request(GATEWAY,data=body,headers=HDR,method='POST')
            with urllib.request.urlopen(req,timeout=60) as r:
                dd=json.loads(r.read())
            A=dd['answers']; pr=A['first_touch']['probabilities']
            res={'choice':A['first_touch']['choice'],
                 'p_cont':float(pr.get('continue_further',0)),
                 'p_rev':float(pr.get('reverse_back',0)),
                 'conf':float(A['conf']['score']),
                 'tok':dd.get('usage',{}).get('inputTokens',0)}
            cache[key]=res; return res
        except Exception as ex:
            last=ex; time.sleep(2*(att+1))
    return {'choice':'ERR','p_cont':None,'p_rev':None,'conf':None,'tok':0,'err':str(last)[:80]}

print(f"\n問 Jev（{len(S)} 筆, 6 執行緒）…", flush=True)
t0=time.perf_counter()
with ThreadPoolExecutor(max_workers=6) as ex:
    res=list(ex.map(jev_call, [r for _,r in S.iterrows()]))
el=time.perf_counter()-t0
json.dump(cache, open(CACHE,'w'))
tok=sum(x.get('tok',0) for x in res)
print(f"{len(res)} 筆，{el:.0f}s（{el/len(res)*1000:.0f} ms/筆），"
      f"{tok} token = ${tok/1e6*0.042:.5f}")

S['jev_choice']=[x['choice'] for x in res]
S['p_cont']=[x['p_cont'] for x in res]
S['p_rev']=[x['p_rev'] for x in res]
S['jev_conf']=[x['conf'] for x in res]
S.to_csv('/tmp/breakout_jev_results.csv',index=False)

print(f"\n=== Jev 答案 ===")
print(pd.Series(S['jev_choice']).value_counts().to_string())
print(f"平均信心: {S['jev_conf'].mean():.2f}/4")

# ── 評估（排除 both/none）──
V=S[S['first'].isin(['cont','fail'])].copy()
V['jev_says_cont']=V['jev_choice']=='continue_further'
V['truth_cont']=V['first']=='cont'
acc=(V['jev_says_cont']==V['truth_cont']).mean()
base=max(V['truth_cont'].mean(), 1-V['truth_cont'].mean())
print(f"\n=== 評估（{len(V)} 筆有效）===")
print(f"Jev 準確率     : {acc:.1%}")
print(f"基準線（多數類）: {base:.1%}")
print(f"→ {'Jev 勝過基準' if acc>base+0.02 else 'Jev 未勝過基準（無技能）'}")
print(f"\nJev 說 cont 的比例: {V['jev_says_cont'].mean():.1%}")
print(f"實際 cont 的比例  : {V['truth_cont'].mean():.1%}")

# 相關性
v2=V.dropna(subset=['p_cont'])
print(f"\ncorr(Jev p_cont, 實際為cont) = "
      f"{np.corrcoef(v2['p_cont'], v2['truth_cont'].astype(float))[0,1]:+.3f}")
print(f"corr(Jev 信心, 判斷正確)      = "
      f"{np.corrcoef(v2['jev_conf'], (v2['jev_says_cont']==v2['truth_cont']).astype(float))[0,1]:+.3f}")
