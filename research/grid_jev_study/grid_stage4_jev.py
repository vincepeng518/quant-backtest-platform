#!/usr/bin/env python3
"""Stage 4: 對真實回測過的 24 個視窗問 Jev（中性提問），
    對照「規則 gate」與「Jev 判斷」誰更能預測真實 PnL。

每個視窗 = 一次請求（state 不可混，已實測）。
真值 = grid_core 實跑 PnL（Stage 3 產出）。
"""
import sys, os, os, json, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
import pandas as pd, numpy as np

KEY=os.environ.get('AI_GATEWAY_API_KEY', '')
G='https://ai-gateway.vercel.sh/v4/ai/evaluation-model'
HDR={'Authorization':f'Bearer {KEY}','Content-Type':'application/json',
     'ai-gateway-protocol-version':'0.0.1','ai-evaluation-model-specification-version':'4',
     'ai-model-id':'typesafe-ai/jev'}

def jev(state,timeout=90,retries=3):
    body=json.dumps({"state":state,"questions":{
        "regime":{"type":"choice",
            "instructions":"接下來 30 天，BTC 更可能屬於哪一種走勢？",
            "criteria":{"range":"來回震盪收斂","trend":"單向推進"}},
        "disp_abs":{"type":"score",
            "instructions":"預估未來 30 天淨位移的絕對幅度",
            "criteria":["<5%","5-10%","10-20%","20-40%",">40%"]},
        "path":{"type":"score","instructions":"預估未來 30 天累積路徑長度（相對淨位移）",
            "criteria":["幾乎直線","路徑略長","路徑明顯長","大幅來回"]},
        "conf":{"type":"score","instructions":"整體把握程度",
            "criteria":["極低","低","中","高","極高"]}}},).encode()
    last=None
    for a in range(retries):
        try:
            req=urllib.request.Request(G,data=body,headers=HDR,method='POST')
            with urllib.request.urlopen(req,timeout=timeout) as r:
                d=json.loads(r.read())
            A=d['answers']
            return {'regime':A['regime']['choice'],
                    'p_trend':A['regime']['probabilities'].get('trend',0),
                    'disp':A['disp_abs']['score'],'path':A['path']['score'],
                    'conf':A['conf']['score'],
                    'tok':d.get('usage',{}).get('inputTokens',0)}
        except Exception as e:
            last=e; time.sleep(2*(a+1))
    return {'regime':'ERR','p_trend':None,'disp':None,'path':None,'conf':None,'tok':0}

S=pd.read_csv('/tmp/grid_real_windows.csv')
print(f"真實回測視窗 {len(S)} 個，問 Jev（中性提問、純數據）…", flush=True)

def build(r):
    return {"asset":"BTC/USDT","timeframe":"daily","close":round(float(r['close']),1),
            "atr_14d":round(float(r['atr']),1),
            "natr":round(float(r['natr']),4),
            "natr_historical_median":round(float(r['natr_thr']),4),
            "adx":round(float(r['adx']),1),
            "plus_di":round(float(r['plus_di']),1),
            "minus_di":round(float(r['minus_di']),1),
            "sma50":round(float(r['sma50']),1),
            "sma200":round(float(r['sma200']),1)}

t0=time.perf_counter()
with ThreadPoolExecutor(max_workers=4) as ex:
    res=list(ex.map(lambda r: jev(build(r)), [r for _,r in S.iterrows()]))
el=time.perf_counter()-t0
tok=sum(x['tok'] for x in res)
print(f"{len(res)} 筆，{el:.0f}s，token {tok} = ${tok/1e6*0.042:.5f}", flush=True)

S['jev_regime']=[x['regime'] for x in res]
S['jev_p_trend']=[x['p_trend'] for x in res]
S['jev_disp']=[x['disp'] for x in res]
S['jev_path']=[x['path'] for x in res]
S['jev_conf']=[x['conf'] for x in res]
S.to_csv('/tmp/grid_jev_final.csv',index=False)

print(f"\n=== Jev 答案 ===")
print(pd.Series(S['jev_regime']).value_counts().to_string())

# ── 真實判準：grid_core 實跑 PnL ──
S['rule_open']=S['natr']>=S['natr_thr']
S['jev_open']=S['jev_regime']=='range'
S['truth']=S['pnl']>0

print(f"\n{'':22}{'開網格':>8}{'PnL>0比例':>11}{'平均PnL':>11}{'總PnL':>10}")
print("-"*64)
for name,col in [('規則', 'rule_open'),('Jev','jev_open')]:
    o=S[S[col]]; c=S[~S[col]]
    if len(o):
        print(f"{name+'：開('+str(len(o))+'個)':22}{'':8}{(o['pnl']>0).mean():>11.1%}{o['pnl'].mean():>11.1f}{o['pnl'].sum():>10.1f}")
    if len(c):
        print(f"{name+'：不開('+str(len(c))+'個)':22}{'':8}{(c['pnl']>0).mean():>11.1%}{c['pnl'].mean():>11.1f}{c['pnl'].sum():>10.1f}")

print(f"\n{'':22}{'準確率':>9}{'精確率':>9}{'召回率':>9}")
print("-"*52)
for name,col in [('規則','rule_open'),('Jev','jev_open')]:
    tp=(S[col]&S['truth']).sum(); fp=(S[col]&~S['truth']).sum()
    fn=(~S[col]&S['truth']).sum()
    acc=(S[col]==S['truth']).mean()
    prec=tp/(tp+fp) if tp+fp else float('nan')
    rec=tp/(tp+fn) if tp+fn else float('nan')
    print(f"{name:22}{acc:>9.1%}{prec:>9.1%}{rec:>9.1%}")

# 策略淨值比較（開網格才有 PnL，不開=0）
print(f"\n=== 策略總 PnL（開網格才計，不開=0）===")
print(f"全開:        {S['pnl'].sum():>9.1f}")
print(f"規則 gate:   {S[S['rule_open']]['pnl'].sum():>9.1f}")
print(f"Jev 判斷:    {S[S['jev_open']]['pnl'].sum():>9.1f}")
print(f"全不開:      {0:>9.1f}")

# 相關性（這次樣本有變異）
print(f"\n=== 預測力（樣本有真實變異）===")
for nm,c in [('jev_p_trend','fwd_disp_pct'),('jev_disp','fwd_disp_pct'),('natr','fwd_disp_pct')]:
    sub=S.dropna(subset=[nm,c])
    print(f"corr({nm}, {c}) = {np.corrcoef(sub[nm],sub[c])[0,1]:+.3f}")
print(f"\nnatr 變異: 標準差 {S['natr'].std():.4f}, 範圍 {S['natr'].min():.4f}~{S['natr'].max():.4f}")
print(f"jv 決策分歧視窗: {((S['rule_open'])!=(S['jev_open'])).sum()} / {len(S)}")
