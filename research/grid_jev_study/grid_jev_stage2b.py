#!/usr/bin/env python3
"""Stage 2b（修正版）: 移除引導文字，改問原子問題。

修正三點：
  1. 不再給「nATR 低 = 趨勢前兆」這種答案提示，只給中性數據
  2. 不問「該不該開網格」（那是推論），改問它被訓練的原子判斷：
     「未來30天是區間盤還是單向趨勢盤」
  3. 判準改用 grid_switcher docstring 的實證 PnL 回歸，不再自訂門檻
"""
import sys, os, os, json, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
import pandas as pd, numpy as np

sys.path.insert(0, '/root/Crypto-Backtesting-Lab')
from engine.strategies.grid_switcher import load_data, compute_indicators

KEY=os.environ.get('AI_GATEWAY_API_KEY', '')
G='https://ai-gateway.vercel.sh/v4/ai/evaluation-model'
HDR={'Authorization':f'Bearer {KEY}','Content-Type':'application/json',
     'ai-gateway-protocol-version':'0.0.1','ai-evaluation-model-specification-version':'4',
     'ai-model-id':'typesafe-ai/jev'}

def jev(state, timeout=60, retries=3):
    """中性提問：不暗示答案，只問方向性判斷。"""
    body=json.dumps({"state":state,"questions":{
        "regime":{"type":"choice",
            "instructions":"未來 30 天，BTC 價格走勢更可能屬於哪一種？",
            "criteria":{"range":"來回震盪，淨位移小於 10%",
                        "trend":"單向推進，淨位移大於 15%"}},
        "disp_size":{"type":"score",
            "instructions":"預估未來 30 天淨位移的絕對幅度（等級）",
            "criteria":["<5%","5-10%","10-15%","15-25%",">25%"]},
        "conf":{"type":"score","instructions":"對上述判斷的把握程度",
            "criteria":["幾乎沒把握","略有把握","中等把握","很有把握","極有把握"]}
    }}).encode()
    last=None
    for a in range(retries):
        try:
            req=urllib.request.Request(G,data=body,headers=HDR,method='POST')
            with urllib.request.urlopen(req,timeout=timeout) as r:
                d=json.loads(r.read())
            A=d['answers']
            return {'regime':A['regime']['choice'],
                    'p_range':A['regime']['probabilities'].get('range',0),
                    'p_trend':A['regime']['probabilities'].get('trend',0),
                    'disp':A['disp_size']['score'],
                    'conf':A['conf']['score'],
                    'tok':d.get('usage',{}).get('inputTokens',0)}
        except Exception as e:
            last=e; time.sleep(2*(a+1))
    return {'regime':'ERR','p_range':None,'p_trend':None,'disp':None,'conf':None,'tok':0}

df = compute_indicators(load_data()).reset_index(drop=True)
D  = pd.read_csv('/tmp/grid_rule_decisions.csv')
# 同一個爭議棒集合，才能直接對照
contested = D[D['gate_contested'] | D['dir_contested']].copy().reset_index(drop=True)
print(f"爭議棒 {len(contested)} 根（與前次同一批），中性提問…", flush=True)

def build_state(r):
    i=int(r['i'])
    rets=[]
    for k in range(10,0,-1):
        if i-k>=0:
            c0=float(df['close'].iloc[i-k]); c1=float(df['close'].iloc[i-k+1])
            rets.append(round((c1-c0)/c0*100,2))
    # 純數據，零引導
    return {"asset":"BTC/USDT","timeframe":"daily","close":round(float(r['close']),1),
            "natr":round(float(r['natr']),4),
            "historical_natr_median":round(float(r['thr']),4),
            "adx":round(float(r['adx']),1),
            "plus_di":round(float(r['pdi']),1),
            "minus_di":round(float(r['mdi']),1),
            "atr":round(float(r['atr']),1),
            "sma50":round(float(r['sma50']),1),
            "sma200":round(float(r['sma200']),1),
            "last_10d_returns_pct":rets}

t0=time.perf_counter()
with ThreadPoolExecutor(max_workers=6) as ex:
    res=list(ex.map(lambda r: jev(build_state(r)), [r for _,r in contested.iterrows()]))
el=time.perf_counter()-t0
print(f"{len(res)} 筆，{el:.0f}s（{el/len(res)*1000:.0f} ms/筆），"
      f"token {sum(x['tok'] for x in res)} = ${sum(x['tok'] for x in res)/1e6*0.042:.5f}", flush=True)

print(f"\n=== Jev regime 分布（中性提問後）===", flush=True)
print(pd.Series([x['regime'] for x in res]).value_counts().to_string(), flush=True)
print(f"平均 p(trend) = {np.mean([x['p_trend'] for x in res if x['p_trend'] is not None]):.3f}", flush=True)
print(f"平均 disp 等級 = {np.mean([x['disp'] for x in res if x['disp'] is not None]):.2f} / 4", flush=True)
print(f"平均信心 = {np.mean([x['conf'] for x in res if x['conf'] is not None]):.2f} / 4", flush=True)

contested['jev_regime']=[x['regime'] for x in res]
contested['jev_p_trend']=[x['p_trend'] for x in res]
contested['jev_disp']=[x['disp'] for x in res]
contested['jev_conf']=[x['conf'] for x in res]

# ── 真值：實證 PnL 回歸（docstring 來源）──
cl=df['close'].values
def outcome(i):
    if i+30>=len(cl): return None
    seg=cl[i:i+31]; disp=(seg[-1]-seg[0])/seg[0]
    path=np.abs(np.diff(seg)).sum()/seg[0]
    return {'disp_pct':abs(disp)*100,'path_pct':path*100,
            'pnl':-0.337*abs(seg[-1]-seg[0])+0.00081*abs(np.diff(seg)).sum()}
outs=[outcome(int(r['i'])) for r in contested.to_dict('records')]
contested['fwd_disp_pct']=[o['disp_pct'] if o else None for o in outs]
contested['fwd_path_pct']=[o['path_pct'] if o else None for o in outs]
contested['pnl_proxy']   =[o['pnl'] if o else None for o in outs]
contested.to_csv('/tmp/grid_jev_verdict2.csv',index=False)

v=contested.dropna(subset=['fwd_disp_pct']).copy()
print(f"\n=== 對照真值（{len(v)} 根）===", flush=True)
v['rule_open']=v['mode'].isin(['range','long','short'])
v['jev_says_range']=v['jev_regime']=='range'

print(f"\n真值分布：位移中位 {v['fwd_disp_pct'].median():.1f}%，"
      f"PnL代理為正比例 {(v['pnl_proxy']>0).mean():.1%}", flush=True)

# 相關性：Jev 的 p(trend) vs 真實位移
sub=v.dropna(subset=['jev_p_trend'])
corr=np.corrcoef(sub['jev_p_trend'], sub['fwd_disp_pct'])[0,1]
print(f"\ncorr( Jev p(trend) , 未來30天實際位移 ) = {corr:+.3f}", flush=True)
corr2=np.corrcoef(sub['jev_disp'], sub['fwd_disp_pct'])[0,1]
print(f"corr( Jev disp等級 , 未來30天實際位移 ) = {corr2:+.3f}", flush=True)

# 規則的 natr 是否能預測位移（原始假設）
corr3=np.corrcoef(v['natr'], v['fwd_disp_pct'])[0,1]
print(f"corr( 規則用的 nATR , 未來30天實際位移 ) = {corr3:+.3f}", flush=True)
print("\n（模組 docstring 記載歷史 corr(natr, 未來30天淨位移) = -0.594）", flush=True)
