#!/usr/bin/env python3
"""Stage 2: 檢驗 5m 突破有沒有任何 edge（在動用 Jev 之前必須先確認）。

問題：Stage 1 顯示突破勝率 31.8% < 隨機 32.8%，兩者都虧。
若連「規則可篩的強突破」都沒 edge，那 Jev 也不會找到東西。

本檔測試：
  1. 用 % 計價（而非價格點數），含真實 fee
  2. 突破強度分層：越強的突破是否勝率越高？
  3. 不同 stop/target 組合
  4. 若無 edge → Jev 無用武之地
"""
import sys
sys.path.insert(0, '/root/Crypto-Backtesting-Lab')
import numpy as np, pandas as pd

df = pd.read_parquet('/tmp/btc_5m.parquet')
n = len(df)
o=df['open'].values; h=df['high'].values; l=df['low'].values; c=df['close'].values
atr=df['atr'].values
print(f"BTC 5m: {n:,} 根")
print(f"ATR 中位: {np.nanmedian(atr):.1f} 點 = {np.nanmedian(atr)/np.nanmedian(c)*100:.3f}% of price")
print(f"fee 單邊 0.05% → 來回 {2*0.05:.2f}% = {2*0.0005*np.nanmedian(c):.1f} 點")
print(f"→ fee 佔 ATR 的 {2*0.0005*np.nanmedian(c)/np.nanmedian(atr)*100:.1f}%")

FEE = 0.0005
def bt(signals, stop_atr, target_atr, max_hold=48, fee=FEE):
    """signals: [(idx, dir)]；回傳 df of trades, pnl 以 % of entry 計"""
    trades=[]; busy=-1
    for idx,d in signals:
        if idx<=busy or idx+1>=n or np.isnan(atr[idx]): continue
        e=idx+1; entry=o[e]; a=atr[idx]
        if a<=0: continue
        stop=entry-d*stop_atr*a; tgt=entry+d*target_atr*a
        ex=None; ei=None; why=None
        for j in range(e, min(e+max_hold, n)):
            if d>0:
                if l[j]<=stop: ex,ei,why=stop,j,'stop'; break
                if h[j]>=tgt:  ex,ei,why=tgt, j,'target'; break
            else:
                if h[j]>=stop: ex,ei,why=stop,j,'stop'; break
                if l[j]<=tgt:  ex,ei,why=tgt, j,'target'; break
        if ex is None: ei=min(e+max_hold-1,n-1); ex=c[ei]; why='time'
        pnl = d*(ex-entry)/entry - 2*fee
        trades.append({'i':e,'dir':d,'entry':entry,'exit':ex,'pnl_pct':pnl*100,
                       'why':why,'bars':ei-e,'R':d*(ex-entry)/(stop_atr*a)})
        busy=ei
    return pd.DataFrame(trades)

def summ(T, label):
    if len(T)==0: return print(f"{label:28s} 無交易")
    print(f"{label:28s} n={len(T):>5}  總 {T['pnl_pct'].sum():>9.1f}%  "
          f"平均 {T['pnl_pct'].mean():>+7.4f}%  勝率 {(T['pnl_pct']>0).mean():>5.1%}  "
          f"平均R {T['R'].mean():>+6.3f}")

print("\n=== 1. 原始突破（全收, 2:1）===")
sigs = sorted([(i,1) for i in np.where(df['brk_up'].values)[0]] +
              [(i,-1) for i in np.where(df['brk_dn'].values)[0]])
summ(bt(sigs,1.5,3.0), "全收 2:1")

print("\n=== 2. 突破強度分層（強度 = 突破幅度/ATR）===")
strength = np.where(df['brk_up'].values, df['brk_strength_up'].values,
           np.where(df['brk_dn'].values, df['brk_strength_dn'].values, np.nan))
for lo,hi in [(0,0.05),(0.05,0.15),(0.15,0.3),(0.3,1.0),(1.0,99)]:
    m = (strength>=lo)&(strength<hi)
    for d_,flag in [(1,'brk_up'),(-1,'brk_dn')]:
        idxs = np.where(m & (df[flag].values))[0]
        if len(idxs)<30: continue
    sel = [(int(i), 1 if df['brk_up'].values[i] else -1) for i in np.where(m)[0]]
    sel.sort()
    summ(bt(sel,1.5,3.0), f"強度 {lo}-{hi}")

print("\n=== 3. 不同 stop/target ===")
for st,tg in [(0.5,1.0),(1.0,1.0),(1.0,2.0),(1.5,1.5),(2.0,2.0),(1.0,3.0),(2.0,4.0)]:
    summ(bt(sigs,st,tg), f"stop {st} / target {tg}")

print("\n=== 4. 隨機進場基準（同筆數, 10 次平均）===")
rng=np.random.default_rng(7)
rnd_pnls=[]
for rep in range(10):
    ri = rng.choice(np.arange(50,n-50), size=3000, replace=False)
    rs = sorted([(int(i), int(rng.choice([1,-1]))) for i in ri])
    T=bt(rs,1.5,3.0)
    rnd_pnls.append(T['pnl_pct'].sum())
print(f"{'隨機 3000 筆 (10 次)':28s} 平均總 {np.mean(rnd_pnls):>9.1f}%  "
      f"範圍 {min(rnd_pnls):.1f} ~ {max(rnd_pnls):.1f}%")

print("\n=== 判讀 ===")
print("若突破全收 ≈ 隨機 → 突破本身無 edge → Jev 也難救")
print("若強突破明顯較好 → 有可篩的結構 → Jev 值得一試")
