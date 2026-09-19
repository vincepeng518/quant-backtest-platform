#!/usr/bin/env python3
"""Stage 3: 兩個關鍵檢驗
  1. 費率敏感度：0.05% (taker) vs 0.02% (maker/VIP) — 結論會不會翻盤
  2. 假突破反向：突破後平均 R 為負 → 反向做是否可行
  3. 突破後續分布：真突破 vs 假突破是否雙峰（若是，Jev 才有可分離的目標）
"""
import sys
sys.path.insert(0,'/root/Crypto-Backtesting-Lab')
import numpy as np, pandas as pd

df = pd.read_parquet('/tmp/btc_5m.parquet')
n=len(df)
o=df['open'].values; h=df['high'].values; l=df['low'].values; c=df['close'].values
atr=df['atr'].values

def bt(signals, stop_atr, target_atr, fee, max_hold=48):
    trades=[]; busy=-1
    for idx,d in signals:
        if idx<=busy or idx+1>=n or np.isnan(atr[idx]): continue
        e=idx+1; entry=o[e]; a=atr[idx]
        if a<=0 or entry<=0: continue
        stop=entry-d*stop_atr*a; tgt=entry+d*target_atr*a
        ex=None; ei=None; why=None
        for j in range(e, min(e+max_hold,n)):
            if d>0:
                if l[j]<=stop: ex,ei,why=stop,j,'stop'; break
                if h[j]>=tgt:  ex,ei,why=tgt,j,'target'; break
            else:
                if h[j]>=stop: ex,ei,why=stop,j,'stop'; break
                if l[j]<=tgt:  ex,ei,why=tgt,j,'target'; break
        if ex is None: ei=min(e+max_hold-1,n-1); ex=c[ei]; why='time'
        trades.append({'i':e,'dir':d,'entry':entry,'exit':ex,
                       'pnl_pct':d*(ex-entry)/entry*100 - 2*fee*100,
                       'pnl_pct_gross':d*(ex-entry)/entry*100,
                       'why':why,'bars':ei-e})
        busy=ei
    return pd.DataFrame(trades)

up=np.where(df['brk_up'].values)[0]; dn=np.where(df['brk_dn'].values)[0]
fwd = sorted([(int(i),1) for i in up]+[(int(i),-1) for i in dn])
rev = sorted([(int(i),-1) for i in up]+[(int(i),1) for i in dn])

print("=== 1. 費率敏感度（stop 2.0 / target 4.0，最佳組合）===")
print(f"{'費率':>18}{'總PnL':>11}{'平均':>10}{'勝率':>8}{'平均R':>9}")
print("-"*58)
for f,label in [(0.0005,'taker 0.05% (來回0.10%)'),
                (0.0002,'maker 0.02% (來回0.04%)'),
                (0.0001,'VIP 0.01% (來回0.02%)'),
                (0.0,   '零費率（純訊號）')]:
    T=bt(fwd,2.0,4.0,f)
    R=d if False else None
    print(f"{label:>18}{T['pnl_pct'].sum():>11.1f}{T['pnl_pct'].mean():>+10.4f}"
          f"{(T['pnl_pct']>0).mean():>8.1%}")

T0=bt(fwd,2.0,4.0,0.0)
print(f"\n零費率下平均 {T0['pnl_pct_gross'].mean():+.4f}%  → "
      f"{'有微弱正訊號' if T0['pnl_pct_gross'].mean()>0 else '訊號本身也不賺'}")

print("\n=== 2. 假突破反向（把突破訊號反過來做）===")
print(f"{'':>18}{'總PnL':>11}{'平均':>10}{'勝率':>8}{'n':>7}")
print("-"*56)
for f,label in [(0.0005,'taker 0.05%'),(0.0002,'maker 0.02%'),(0.0,'零費率')]:
    T=bt(rev,2.0,4.0,f)
    print(f"{label:>18}{T['pnl_pct'].sum():>11.1f}{T['pnl_pct'].mean():>+10.4f}"
          f"{(T['pnl_pct']>0).mean():>8.1%}{len(T):>7}")

print("\n=== 3. 突破後續分布：真突破 vs 假突破 是否雙峰 ===")
# 定義：突破後 48 根內，是否達到 2*ATR 延續（真） vs 先回到 1*ATR 反向（假）
rows=[]
for i,d in fwd:
    if i+1>=n or np.isnan(atr[i]): continue
    e=i+1; entry=o[e]; a=atr[i]
    if a<=0 or entry<=0: continue
    hi48 = h[e:min(e+48,n)].max(); lo48 = l[e:min(e+48,n)].min()
    if d>0:
        cont = (hi48-entry)/a;  fail = (entry-lo48)/a
    else:
        cont = (entry-lo48)/a;  fail = (hi48-entry)/a
    rows.append({'i':i,'dir':d,'cont_atr':cont,'fail_atr':fail,
                 'net_48': d*(c[min(e+47,n-1)]-entry)/a})
F=pd.DataFrame(rows)
print(f"n={len(F)}")
print(f"  延續幅度(ATR) 中位 {F['cont_atr'].median():.2f}, 均值 {F['cont_atr'].mean():.2f}")
print(f"  回撤幅度(ATR) 中位 {F['fail_atr'].median():.2f}, 均值 {F['fail_atr'].mean():.2f}")
print(f"  48根後淨位移(ATR) 中位 {F['net_48'].median():.3f}, 均值 {F['net_48'].mean():.3f}")
big_cont = (F['cont_atr']>=2.0).mean(); big_fail=(F['fail_atr']>=2.0).mean()
print(f"  達 2ATR 延續: {big_cont:.1%}   達 2ATR 反向: {big_fail:.1%}")
print(f"  → {'雙峰明顯（Jev 有可分離目標）' if big_cont>0.25 and big_fail>0.25 else '非雙峰（Jev 無明確目標）'}")
F.to_csv('/tmp/breakout_outcomes.csv',index=False)

print("\n=== 4. 有沒有任何可用的盤前特徵？===")
feat = df.iloc[[int(i) for i in F['i']]][['adx' if 'adx' in df.columns else 'atr']].copy()
sub=df.iloc[F['i'].values].reset_index(drop=True)
F=F.reset_index(drop=True)
# 看突破時的相對位置、波動狀態
sub2=sub.copy()
sub2['brk_atr']=np.where(F['dir']>0, sub2['brk_strength_up'], sub2['brk_strength_dn'])
sub2['atr_pct']=sub2['atr']/sub2['close']*100
sub2['range_pos']=(sub2['close']-sub2['don_lo'])/(sub2['don_hi']-sub2['don_lo']).replace(0,np.nan)
for col in ['brk_atr','atr_pct','ret_1','ret_12','ret_48']:
    v=sub2[col].values
    ok=~np.isnan(v)
    if ok.sum()>100:
        cr=np.corrcoef(v[ok], F['net_48'].values[ok])[0,1]
        print(f"  corr({col:10s}, 48根後淨位移) = {cr:+.3f}")
