"""
combo_explorer.py v2 — 挖掘「意想不到、適合手動 P&L 交易者」的指標組合。
- 擴充：更多候選指標 + 參數掃描 + 組合交叉
- 驚喜評分：Sharpe>0.8 且 最大回撤>-0.4 且 與 buy&hold 相關<0.5（非直覺/低相關）
- 每輪輸出 Top 驚喜組合到 findings.md
"""
import os, sys, json, math, datetime
import numpy as np
import pandas as pd
from itertools import combinations

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CSV = os.path.join(ROOT, "research", "btc_usdt_1d.csv")
FIND = os.path.join(ROOT, "research", "combo_findings.md")

def load():
    df = pd.read_csv(CSV)
    colmap = {}
    for c in df.columns:
        cl = c.lower()
        if cl in ("open","o"): colmap[c]="open"
        elif cl in ("high","h"): colmap[c]="high"
        elif cl in ("low","l"): colmap[c]="low"
        elif cl in ("close","c"): colmap[c]="close"
        elif cl in ("volume","vol","v"): colmap[c]="volume"
    df = df.rename(columns=colmap)
    key = "open_time" if "open_time" in df.columns else df.columns[0]
    df = df.sort_values(key).reset_index(drop=True)
    return df

def sma(s,n): return s.rolling(n).mean()
def rma(s,n):
    a=1/n; out=np.full(len(s),np.nan)
    for i in range(len(s)):
        out[i]=s.iloc[0] if i==0 else a*s.iloc[i]+(1-a)*out[i-1]
    return pd.Series(out,index=s.index)
def atr(df,n=14):
    h,l,c=df["high"],df["low"],df["close"]; pc=c.shift(1)
    tr=pd.concat([(h-l),(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
    return rma(tr,n)
def adx(df,n=14):
    h,l,c=df["high"],df["low"],df["close"]
    up=h.diff(); dn=l.diff()
    pp=up.where((up>0)&(up>dn),0.0); pm=dn.where((dn>0)&(dn>up),0.0)
    tr=pd.concat([(h-l),(h-c.shift(1)).abs(),(l-c.shift(1)).abs()],axis=1).max(axis=1)
    atr_=rma(tr,n); pdi=100*rma(pp,n)/atr_; mdi=100*rma(pm,n)/atr_
    dx=(pdi-mdi).abs()/(pdi+mdi).replace(0,np.nan)*100
    return rma(dx,n),pdi,mdi
def donchian(h,l,n):
    hi=h.rolling(n).max(); lo=l.rolling(n).min()
    return (hi+lo)/2,hi,lo
def kc(h,l,c,n=20,mult=2):
    mid=sma((h+l+c)/3,n); r=mult*(h-l).rolling(n).mean()
    return mid+r,mid,mid-r
def vwap(df):
    v=df["volume"]; tp=(df["high"]+df["low"]+df["close"])/3
    return (tp*v).cumsum()/v.cumsum()
def rsi(s,n=14):
    d=s.diff(); g=d.clip(lower=0); ls=(-d).clip(lower=0)
    rs=rma(g,n)/rma(ls,n); return 100-100/(1+rs)
def supertrend(df,n=10,mult=3):
    atr_=atr(df,n); mid=(df["high"]+df["low"])/2
    up=mid+mult*atr_; dn=mid-mult*atr_
    st=np.full(len(df),np.nan); d=np.full(len(df),1)
    for i in range(1,len(df)):
        d[i]=1 if df["close"].iloc[i]>up.iloc[i-1] else (-1 if df["close"].iloc[i]<dn.iloc[i-1] else d[i-1])
        up.iloc[i]=min(up.iloc[i],up.iloc[i-1]) if d[i]==1 else up.iloc[i]
        dn.iloc[i]=max(dn.iloc[i],dn.iloc[i-1]) if d[i]==-1 else dn.iloc[i]
        st[i]=dn.iloc[i] if d[i]==1 else up.iloc[i]
    return pd.Series(st,index=df.index),pd.Series(d,index=df.index)
def vol_z(v,n=20):
    m=v.rolling(n).mean(); sd=v.rolling(n).std()
    return (v-m)/sd
def ichimoku(df,ten=9,kij=26,sen=52):
    tenk=(df["high"].rolling(ten).max()+df["high"].rolling(ten).min())/2
    kij=(df["high"].rolling(kij).max()+df["high"].rolling(kij).min())/2
    senk=(df["high"].rolling(sen).max()+df["high"].rolling(sen).min())/2
    return tenk,kij,senk

def backtest(sig,close,fee=0.001):
    rets=[]; pos=0
    sig=np.asarray(sig); cl=np.asarray(close)
    for i in range(1,len(cl)):
        tgt=sig[i-1]; 
        if tgt!=pos and tgt!=0:
            r=(cl[i]/cl[i-1]-1)*tgt-fee
        else:
            r=(cl[i]/cl[i-1]-1)*pos
        rets.append(r); pos=tgt
    rets=np.array(rets); eq=np.cumprod(1+rets)
    sharpe=rets.mean()/rets.std()*np.sqrt(365) if rets.std()>0 else 0
    mdd=(eq/np.maximum.accumulate(eq)-1).min()
    win=(rets>0).mean()
    ann=(eq[-1]**(365/len(rets))-1) if len(rets)>0 else 0
    return {"sharpe":round(float(sharpe),2),"mdd":round(float(mdd),3),"win":round(float(win),3),"ann":round(float(ann),3),"n_trades":int((np.diff(sig)!=0).sum())}

def base_signals(df):
    c,h,l=df["close"],df["high"],df["low"]; v=df["volume"]
    S={}
    a,pdi,mdi=adx(df)
    vw=vwap(df); st,st_dir=supertrend(df)
    r=rsi(c); vz=vol_z(v); atr_=atr(df)
    tenk,kij,senk=ichimoku(df); spanA=(tenk+senk)/2
    mom=c.pct_change(5)
    # 基礎指標（多參數變體）
    for n in (10,20,30):
        _,dhi,dlo=donchian(h,l,n)
        S[f"Donchian{n}"]=np.where(c>dhi.shift(1),1,np.where(c<dlo.shift(1),-1,0))
    for n in (14,25):
        aa,_,_=adx(df,n)
        S[f"ADX{n}"]=np.where(aa>25,np.where(pdi>mdi,1,-1),0)
    for mult in (1.5,2.0,2.5):
        upper=v+mult*atr_; lower=v-mult*atr_
        S[f"VWAP_ATR{mult}"]=np.where(c>upper,1,np.where(c<lower,-1,0))
    S["VWAP"]=np.where(c<vw*0.98,1,np.where(c>vw*1.02,-1,0))
    S["Supertrend"]=st_dir.values
    _,khi,klo=kc(h,l,c)
    S["KC"]=np.where(c>khi.shift(1),1,np.where(c<klo.shift(1),-1,0))
    S["RSI"]=np.where(r<30,1,np.where(r>70,-1,0))
    S["Ichimoku"]=np.where((c>spanA)&(c>kij),1,np.where((c<spanA)&(c<kij),-1,0))
    S["VolZ"]=np.where(vz>2,1,np.where(vz<-2,-1,0))
    S["Mom"]=np.where(mom>0,1,np.where(mom<0,-1,0))
    # ---- 交叉組合（意想不到） ----
    # 1. ADX 過濾 Donchian（只在大趨勢濾波下做突破）
    for n in (10,20,30):
        _,dhi,dlo=donchian(h,l,n)
        S[f"ADXxDonchian{n}"]=np.where(a>20,np.where(c>dhi.shift(1),1,np.where(c<dlo.shift(1),-1,0)),0)
    # 2. VWAP + VolZ（量異常才做 VWAP 回歸）
    S["VWAPxVolZ"]=np.where(vz.abs()>1.5,S["VWAP"],0)
    # 3. Supertrend + RSI 過濾
    S["STxRSI"]=np.where((st_dir==1)&(r<45),1,np.where((st_dir==-1)&(r>55),-1,0))
    # 4. Ichimoku + ADX
    S["IchxADX"]=np.where((c>spanA)&(a>25),1,np.where((c<spanA)&(a>25),-1,0))
    # 5. KC breakout + VolZ 確認
    S["KCxVolZ"]=np.where((c>khi.shift(1))&(vz>1),1,np.where((c<klo.shift(1))&(vz>1),-1,0))
    # 6. Donchian 反向濾波（假突破）
    _,dhi,dlo=donchian(h,l,20)
    S["DonchianAntiVol"]=np.where((c>dhi.shift(1))&(vz<-1),-1,np.where((c<dlo.shift(1))&(vz<-1),1,0))
    # 7. RSI + Supertrend 背離
    S["RSIxSTdiv"]=np.where((st_dir==1)&(r>70),-1,np.where((st_dir==-1)&(r<30),1,0))
    # 8. Mom + ADX
    S["MomxADX"]=np.where(a>25,S["Mom"],0)
    # 9. Ichimoku + VolZ
    S["IchxVolZ"]=np.where((c>spanA)&(vz>1.5),1,np.where((c<spanA)&(vz>1.5),-1,0))
    # 10. Supertrend + VolZ
    S["STxVolZ"]=np.where((st_dir==1)&(vz>1),1,np.where((st_dir==-1)&(vz>1),-1,0))
    # 11. VWAP_ATR + ADX（通道突破要趨勢強）
    for mult in (1.5,2.0):
        upper=v+mult*atr_; lower=v-mult*atr_
        S[f"VWAP_ATRxADX{mult}"]=np.where(a>25,np.where(c>upper,1,np.where(c<lower,-1,0)),0)
    # 12. KC + ADX
    S["KCxADX"]=np.where(a>25,S["KC"],0)
    # 13. Donchian + Mom（突破且動量同向）
    for n in (10,20):
        _,dhi,dlo=donchian(h,l,n)
        S[f"DonchianxMom{n}"]=np.where((c>dhi.shift(1))&(mom>0),1,np.where((c<dlo.shift(1))&(mom<0),-1,0))
    # 14. RSI + VolZ（超買超賣 + 量確認）
    S["RSIxVolZ"]=np.where((r<30)&(vz>1),1,np.where((r>70)&(vz>1),-1,0))
    # 15. Ichimoku + Mom
    S["IchxMom"]=np.where((c>spanA)&(mom>0),1,np.where((c<spanA)&(mom<0),-1,0))
    return {k:pd.Series(v,index=df.index) for k,v in S.items()}

def main(round_idx=0):
    df=load(); S=base_signals(df); close=df["close"].values
    res={}; eqs={}
    for name,s in S.items():
        try:
            r=backtest(s.values,close); res[name]=r; eqs[name]=np.cumprod(1+np.array([(close[i]/close[i-1]-1)*(s.values[i-1] if i>1 else 0) for i in range(1,len(close))]))
        except Exception as e:
            res[name]={"error":str(e)[:80]}
    # buy&hold 基準
    bh=df["close"].pct_change().dropna().values; eq_bh=np.cumprod(1+bh)
    res["__BUYHOLD__"]=backtest(np.ones(len(close)),close)
    # 驚喜評分：與 BH 相關低 + sharpe 高 + mdd 可控（放寬：>=2 即記錄）
    惊喜=[]; weak=[]
    for name,r in res.items():
        if name.startswith("__") or "error" in r: continue
        eq=eqs.get(name)
        if eq is None or len(eq)<10: continue
        corr=float(np.corrcoef(eq,eq_bh)[0,1]) if not np.isnan(eq_bh).any() else 0
        score=0
        if r["sharpe"]>=0.8: score+=1
        if r["mdd"]>=-0.4: score+=1
        if abs(corr)<0.5: score+=1
        if r["n_trades"]>=10: score+=1
        if score>=3: 惊喜.append((name,r,round(corr,2),score))
        elif score>=2: weak.append((name,r,round(corr,2),score))
    惊喜.sort(key=lambda x:-x[3]); weak.sort(key=lambda x:-x[3])
    ts=datetime.datetime.now().strftime("%m-%d %H:%M")
    out=f"\n## [{ts}] round {round_idx} (combos tested: {len([n for n in res if not n.startswith('__')])})\n"
    out+=f"**強驚喜 (score>=3):**\n\n" if 惊喜 else f"**強驚喜:** 無\n\n"
    for name,r,corr,sc in 惊喜[:12]:
        out+=f"- `{name}`: Sharpe={r['sharpe']} | MDD={r['mdd']} | win={r['win']} | ann={r['ann']} | corr_BH={corr} | trades={r['n_trades']} | score={sc}\n"
    if weak:
        out+="\n**弱驚喜 (score=2, 待觀察):**\n\n"
        for name,r,corr,sc in weak[:10]:
            out+=f"- `{name}`: Sharpe={r['sharpe']} | MDD={r['mdd']} | corr_BH={corr} | trades={r['n_trades']}\n"
    out+="\n"
    with open(FIND,"a") as f: f.write(out)
    print(out)
    return 惊喜

if __name__=="__main__":
    ri=int(sys.argv[1]) if len(sys.argv)>1 else 0
    main(ri)
