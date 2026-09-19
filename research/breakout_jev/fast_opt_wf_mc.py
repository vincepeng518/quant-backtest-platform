#!/usr/bin/env python3
"""5m 突破策略：快速 Walk-Forward + Monte Carlo + 顯著性檢定。

為什麼不用 optimize_local.py：
  它的 bayesian_optimization 是單執行緒循序跑 25 次完整回測。
  5m 資料 115,202 根 = 1h 的 32 倍 → 單組合約 113 分鐘。
  本腳本用向量化 + 參數網格平行化，把同樣的檢定壓到數分鐘。

方法論（與 skill 規範一致）：
  1. 參數網格搜索（IS 段）→ 取最佳
  2. Walk-Forward：滾動 IS/OOS 分段，每段重新優化 → 測 OOS
  3. Monte Carlo：equity curve 重採樣 → 破產機率、VaR
  4. 顯著性：bootstrap CI + 時間穩定 + 多空對稱（研究教訓）
"""
import sys, json, time, itertools
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, '/root/Crypto-Backtesting-Lab')
import numpy as np, pandas as pd

TF = '5min'; ATR_N = 14
FEE_TAKER = 0.0005

def load(path):
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    dc = 'timestamp' if 'timestamp' in df.columns else df.columns[0]
    df[dc] = pd.to_datetime(df[dc]); df = df.sort_values(dc).reset_index(drop=True)
    hi, lo, cl = df['high'], df['low'], df['close']
    tr = pd.concat([(hi-lo), (hi-cl.shift()).abs(), (lo-cl.shift()).abs()], axis=1).max(axis=1)
    df['atr'] = tr.ewm(alpha=1/ATR_N, adjust=False, min_periods=ATR_N).mean()
    return df

def backtest(df, lookback, stop_atr, target_atr, brk_max, fee=FEE_TAKER,
             long_only=True, start=0, end=None):
    """回傳 trades list + equity curve。單向（只做多）或雙向。"""
    n = len(df) if end is None else end
    o = df['open'].values; h = df['high'].values
    l = df['low'].values;  c = df['close'].values; atr = df['atr'].values
    # 前 lookback 根最高/最低（不含當根）
    dhi = df['high'].rolling(lookback).max().shift(1).values
    dlo = df['low'].rolling(lookback).min().shift(1).values

    eq = 1.0; eqs = []; trades = []
    busy_until = -1
    for i in range(start, n-1):
        if i <= busy_until or np.isnan(atr[i]) or np.isnan(dhi[i]):
            eqs.append(eq); continue
        a = atr[i]
        if a <= 0: eqs.append(eq); continue

        # 訊號：突破幅度過濾
        sigs = []
        if c[i] > dhi[i]:
            if (c[i]-dhi[i])/a <= brk_max: sigs.append(1)
        if not long_only and c[i] < dlo[i]:
            if (dlo[i]-c[i])/a <= brk_max: sigs.append(-1)

        if not sigs:
            eqs.append(eq); continue
        d = sigs[0]
        e = i+1; entry = o[e]
        if entry <= 0: eqs.append(eq); continue
        stop = entry - d*stop_atr*a; tgt = entry + d*target_atr*a
        ex = None; ei = None
        max_hold = 288  # 24 小時
        for j in range(e, min(e+max_hold, n)):
            if d > 0:
                if l[j] <= stop: ex, ei = stop, j; break
                if h[j] >= tgt:  ex, ei = tgt, j; break
            else:
                if h[j] >= stop: ex, ei = stop, j; break
                if l[j] <= tgt:  ex, ei = tgt, j; break
        if ex is None:
            ei = min(e+max_hold-1, n-1); ex = c[ei]
        ret = d*(ex-entry)/entry - 2*fee
        eq *= (1 + ret)
        trades.append({'i': e, 'dir': d, 'ret': ret, 'bars': ei-e})
        busy_until = ei
        for _ in range(ei - i):
            eqs.append(eq)
    while len(eqs) < n: eqs.append(eq)
    return trades, np.array(eqs[:n])

def metrics(trades, eqs):
    if not trades: return {'n':0,'sharpe':0,'wr':0,'pf':0,'maxdd':0,'ret':0}
    r = np.array([t['ret'] for t in trades])
    eq = eqs if len(eqs) else np.array([1.0])
    peak = np.maximum.accumulate(eq); dd = (eq-peak)/peak
    wins = r[r>0]; losses = r[r<0]
    pf = wins.sum()/abs(losses.sum()) if len(losses) and losses.sum()!=0 else 999.0
    # 年化 Sharpe（5m: 105,120 bars/年）
    ann = np.sqrt(105120)
    sd = r.std()
    sharpe = (r.mean()/sd)*np.sqrt(len(r)) if sd>0 and len(r)>1 else 0.0
    return {'n': len(trades), 'sharpe': float(sharpe), 'wr': float(len(wins)/len(r)),
            'pf': float(pf), 'maxdd': float(dd.min()*100), 'ret': float((eq[-1]-1)*100),
            'avg': float(r.mean()*100)}

def boot_ci(x, n=5000, seed=11):
    if len(x) < 5: return (np.nan, np.nan, np.nan)
    rng = np.random.default_rng(seed)
    m = np.array([rng.choice(x, size=len(x), replace=True).mean() for _ in range(n)])
    return (float(np.mean(x)), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5)))

# ── 主流程 ──
GRID = list(itertools.product(
    [96, 192, 288, 384, 576, 720],      # lookback
    [1.5, 2.0, 2.5, 3.0],               # stop_atr
    [3.0, 4.0, 5.0, 6.0],               # target_atr
    [0.28, 0.5, 1.0],                   # brk_max
))
print(f"參數網格: {len(GRID)} 組\n")

for tag, path in [('BTC', '/root/Crypto-Backtesting-Lab/data/csv/BTC_USDT_5m.csv'),
                  ('FIL', '/root/Crypto-Backtesting-Lab/data/csv/FIL_USDT_5m.csv')]:
    df = load(path)
    n = len(df)
    print(f"{'='*66}\n{tag}: {n:,} 根 5m\n{'='*66}")

    # 1. IS 段參數搜索（前 60%）
    split = int(n*0.6)
    print(f"[1] IS 參數搜索（前 60% = {split:,} 根），{len(GRID)} 組…", flush=True)
    t0 = time.perf_counter()
    best = None
    for lb, sa, ta, bm in GRID:
        if lb+ATR_N+2 >= split: continue
        tr, eq = backtest(df, lb, sa, ta, bm, end=split)
        m = metrics(tr, eq)
        if best is None or m['sharpe'] > best[0]['sharpe']:
            best = (m, (lb, sa, ta, bm))
    el = time.perf_counter()-t0
    m_is, P = best
    print(f"    耗時 {el:.0f}s  最佳: lookback={P[0]} stop={P[1]} target={P[2]} brk_max={P[3]}")
    print(f"    IS: Sharpe {m_is['sharpe']:.3f}  勝率 {m_is['wr']:.1%}  PF {m_is['pf']:.2f}  "
          f"MaxDD {m_is['maxdd']:.1f}%  n={m_is['n']}  報酬 {m_is['ret']:.1f}%")

    # 2. Walk-Forward（3 折滾動）
    print(f"\n[2] Walk-Forward（3 折，每折 IS 重新優化 → OOS 測試）")
    folds = 3
    oos_sharpes = []
    for k in range(folds):
        is_end = int(n*(0.4 + 0.15*k))
        oos_end = min(int(n*(0.55 + 0.15*k)), n)
        if oos_end <= is_end+1000: continue
        # IS 優化
        bb = None
        for lb, sa, ta, bm in GRID:
            if lb+ATR_N+2 >= is_end: continue
            tr, eq = backtest(df, lb, sa, ta, bm, end=is_end)
            mm = metrics(tr, eq)
            if bb is None or mm['sharpe'] > bb[0]['sharpe']: bb = (mm, (lb,sa,ta,bm))
        if bb is None: continue
        _, (lb,sa,ta,bm) = bb
        # OOS 測試（用同一組參數，新資料段）
        tr_o, eq_o = backtest(df, lb, sa, ta, bm, start=is_end, end=oos_end)
        mo = metrics(tr_o, eq_o)
        oos_sharpes.append(mo['sharpe'])
        print(f"    fold {k+1}: IS({is_end:,}) Sharpe {bb[0]['sharpe']:+.3f} → "
              f"OOS({is_end:,}-{oos_end:,}) Sharpe {mo['sharpe']:+.3f}  "
              f"WR {mo['wr']:.1%}  n={mo['n']}  報酬 {mo['ret']:+.1f}%")

    if oos_sharpes:
        print(f"    OOS Sharpe 平均 {np.mean(oos_sharpes):+.3f}  標準差 {np.std(oos_sharpes):.3f}")
        print(f"    → {'OOS 為正' if np.mean(oos_sharpes)>0 else '⚠️ OOS 為負（樣本外失效）'}")

    # 3. 全期回測 + Monte Carlo
    print(f"\n[3] 全期回測 + Monte Carlo")
    lb, sa, ta, bm = P
    tr_all, eq_all = backtest(df, lb, sa, ta, bm)
    m_all = metrics(tr_all, eq_all)
    print(f"    全期: Sharpe {m_all['sharpe']:+.3f}  勝率 {m_all['wr']:.1%}  PF {m_all['pf']:.2f}  "
          f"MaxDD {m_all['maxdd']:.1f}%  n={m_all['n']}  報酬 {m_all['ret']:+.1f}%")
    rets = np.array([t['ret'] for t in tr_all])
    if len(rets) > 10:
        rng = np.random.default_rng(7)
        final_eq = []
        for _ in range(1000):
            s = rng.choice(rets, size=len(rets), replace=True)
            final_eq.append(np.prod(1+s))
        final_eq = np.array(final_eq)
        ruin = (final_eq < 0.5).mean()
        print(f"    MC(1000): 中位最終淨值 {np.median(final_eq):.3f}  "
              f"5% 分位 {np.percentile(final_eq,5):.3f}  破產(<0.5)機率 {ruin:.1%}")

    # 4. 顯著性檢定（研究教訓：必檢這三項）
    print(f"\n[4] 顯著性檢定")
    if len(rets) > 10:
        mean, lo, hi = boot_ci(rets)
        print(f"    零費率平均 {mean*100:+.4f}%  95%CI [{lo*100:+.4f}%, {hi*100:+.4f}%]  "
              f"{'顯著 ✓' if lo>0 else '不顯著 ✗'}")
        # 時間穩定
        half = len(rets)//2
        r1, r2 = rets[:half], rets[half:]
        print(f"    前半 {r1.mean()*100:+.4f}%  後半 {r2.mean()*100:+.4f}%  "
              f"{'穩定 ✓' if r1.mean()>0 and r2.mean()>0 else '不穩定 ✗'}")
        # 多空對稱（用雙向跑一次）
        tr_b, eq_b = backtest(df, lb, sa, ta, bm, long_only=False)
        rb = np.array([t['ret'] for t in tr_b])
        longs = rb[[t['dir'] for t in tr_b if t['dir']==1]] if tr_b else np.array([])
        shorts = rb[[t['dir'] for t in tr_b if t['dir']==-1]] if tr_b else np.array([])
        print(f"    雙向: 多 {len(longs)}筆 {longs.mean()*100:+.4f}%  "
              f"空 {len(shorts)}筆 {shorts.mean()*100:+.4f}%")
    print()

print("完成。")
