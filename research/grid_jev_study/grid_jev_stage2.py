#!/usr/bin/env python3
"""Stage 2: 對爭議棒問 Jev，然後用「未來 30 天實際走勢」評判規則 vs Jev 誰對。

關鍵約束（實測得知）：同請求內所有問題共用同一個 state
→ 一根棒 = 一次請求，不能批次。

評判標準（來自 grid_switcher 模組 docstring 的實證回歸）：
  30天網格PnL = 773 - 0.337 x |淨位移| + 0.00081 x 路徑長度
→ 網格怕「單向位移」。位移大 = 該空手；位移小 + 路徑長 = 適合收租。
"""
import sys, os, os, json, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
import pandas as pd, numpy as np

sys.path.insert(0, '/root/Crypto-Backtesting-Lab')
from engine.strategies.grid_switcher import load_data, compute_indicators, decide

KEY=os.environ.get('AI_GATEWAY_API_KEY', '')
G='https://ai-gateway.vercel.sh/v4/ai/evaluation-model'
HDR={'Authorization':f'Bearer {KEY}','Content-Type':'application/json',
     'ai-gateway-protocol-version':'0.0.1','ai-evaluation-model-specification-version':'4',
     'ai-model-id':'typesafe-ai/jev'}

def jev(state, timeout=60, retries=3):
    body=json.dumps({"state":state,"questions":{
        "grid":{"type":"choice","instructions":"以未來 30 天而言，這個市場狀態適合開網格區間收租，還是應該空手等待？",
                "criteria":{"open_grid":"區間震盪為主，適合收租",
                            "stay_flat":"單向位移風險高，應空手"}},
        "conf":{"type":"score","instructions":"你對這個判斷的把握程度",
                "criteria":["幾乎沒把握","略有把握","中等把握","很有把握","極有把握"]},
        "trending":{"type":"boolean","instructions":"接下來傾向單向趨勢盤而非區間盤",
                    "criteria":{"yes":"單向趨勢"}}
    }}).encode()
    last=None
    for a in range(retries):
        try:
            req=urllib.request.Request(G,data=body,headers=HDR,method='POST')
            with urllib.request.urlopen(req,timeout=timeout) as r:
                d=json.loads(r.read())
            A=d['answers']
            return {'grid':A['grid']['choice'],
                    'p_flat':A['grid']['probabilities'].get('stay_flat',0),
                    'conf':A['conf']['score'],
                    'p_trend':A['trending'].get('probability',0),
                    'tok':d.get('usage',{}).get('inputTokens',0)}
        except Exception as e:
            last=e; time.sleep(2*(a+1))
    return {'grid':'ERR','p_flat':None,'conf':None,'p_trend':None,'tok':0,'err':str(last)[:60]}

# ── 準備資料 ──
df = compute_indicators(load_data()).reset_index(drop=True)
D = pd.read_csv('/tmp/grid_rule_decisions.csv')
contested = D[D['gate_contested'] | D['dir_contested']].copy()
print(f"爭議棒 {len(contested)} 根，開始問 Jev（6 執行緒）…", flush=True)

def build_state(r):
    i=int(r['i']); close=float(r['close'])
    # 近 5 日漲跌，給 Jev 一點路徑資訊（規則本身只看當下）
    rets=[]
    for k in range(5,0,-1):
        if i-k>=0:
            c0=float(df['close'].iloc[i-k]); c1=float(df['close'].iloc[i-k+1])
            rets.append(round((c1-c0)/c0*100,2))
    return {"market":"BTC/USDT 日線",
            "close":round(close,1),
            "natr":round(float(r['natr']),4),
            "natr_median_threshold":round(float(r['thr']),4),
            "adx":round(float(r['adx']),1),
            "plus_di":round(float(r['pdi']),1),
            "minus_di":round(float(r['mdi']),1),
            "atr":round(float(r['atr']),1),
            "sma50":round(float(r['sma50']),1),
            "sma200":round(float(r['sma200']),1),
            "last_5d_returns_pct":rets,
            "note":("nATR 低於歷史中位數代表波動壓縮，過去實測為趨勢前兆；"
                    "單向位移會輾壓網格。請判斷未來30天是區間或單向。")}

t0=time.perf_counter()
with ThreadPoolExecutor(max_workers=6) as ex:
    results=list(ex.map(lambda r: jev(build_state(r)), [r for _,r in contested.iterrows()]))
el=time.perf_counter()-t0
print(f"完成 {len(results)} 筆，耗時 {el:.0f}s（{el/len(results)*1000:.0f} ms/筆）", flush=True)

contested=contested.reset_index(drop=True)
contested['jev_grid']=[x['grid'] for x in results]
contested['jev_p_flat']=[x['p_flat'] for x in results]
contested['jev_conf']=[x['conf'] for x in results]
contested['jev_p_trend']=[x['p_trend'] for x in results]
tot_tok=sum(x['tok'] for x in results)
print(f"token: {tot_tok} → 成本 ${tot_tok/1e6*0.042:.5f}", flush=True)

# ── 未來 30 天實際走勢（評判用，決策時未使用）──
cl=df['close'].values
def outcome(i):
    if i+30>=len(cl): return None
    seg=cl[i:i+31]
    disp=(seg[-1]-seg[0])/seg[0]
    path=np.abs(np.diff(seg)).sum()/seg[0]
    return {'fwd_30_disp_pct':round(abs(disp)*100,2),'fwd_30_path_pct':round(path*100,2),
            'grid_pnl_proxy':round(-0.337*abs(seg[-1]-seg[0])+0.00081*abs(np.diff(seg)).sum(),1)}
outs=[outcome(int(r['i'])) for r in contested.to_dict('records')]
contested['fwd_30_disp_pct']=[o['fwd_30_disp_pct'] if o else None for o in outs]
contested['fwd_30_path_pct']=[o['fwd_30_path_pct'] if o else None for o in outs]
contested['grid_pnl_proxy']=[o['grid_pnl_proxy'] if o else None for o in outs]

contested.to_csv('/tmp/grid_jev_verdict.csv', index=False)
print("已存 /tmp/grid_jev_verdict.csv", flush=True)

# ── 對照 ──
v=contested.dropna(subset=['fwd_30_disp_pct']).copy()
v['rule_open']=v['mode'].isin(['range','long','short'])
v['jev_open']=v['jev_grid']=='open_grid'
print(f"\n=== 規則 vs Jev（{len(v)} 根有未來資料）===", flush=True)
print(v[['rule_open','jev_open']].value_counts().to_string(), flush=True)
agree=(v['rule_open']==v['jev_open']).mean()
print(f"\n一致率: {agree:.1%}", flush=True)

# 用未來位移判對錯：位移 > 15% = 該空手
TH=15.0
v['truth_open']=v['fwd_30_disp_pct'] < TH   # 位移小 → 適合開
print(f"\n=== 以「未來30天位移 < {TH}% 則該開網格」為判準 ===", flush=True)
for name,col in [('規則','rule_open'),('Jev','jev_open')]:
    acc=(v[col]==v['truth_open']).mean()
    print(f"{name}: 準確率 {acc:.1%}", flush=True)
print(f"（註：判準為單一門檻代理，非真 PnL；位移中位 {v['fwd_30_disp_pct'].median():.1f}%）", flush=True)
