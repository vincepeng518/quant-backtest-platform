#!/usr/bin/env python3
"""Stage 1: 5m 突破策略 — 純規則基線。

設計：Donchian 突破 + ATR 停損停利。
Jev 的位子：5m 突破最大的敵人是「假突破」，規則只會說「價格破了前高」，
分不出真破還是假破。這正是 Jev 該判斷的事。

本檔先建立基線與訊號量（決定 Jev 要打幾次）。
"""
import sys
sys.path.insert(0, '/root/Crypto-Backtesting-Lab')
import numpy as np, pandas as pd

TF = '5min'
LOOKBACK = 24        # Donchian 回看 24 根 5m = 2 小時
ATR_N = 14
STOP_ATR = 1.5
TARGET_ATR = 3.0     # 2:1 R:R
MAX_HOLD = 48        # 最長持倉 4 小時
FEE = 0.0005         # 單邊 0.05%（taker，保守）

def load_5m(path, name):
    M = pd.read_parquet(path)
    dc = [c for c in M.columns if c.lower() in ('dt','timestamp','time','date')][0]
    M[dc] = pd.to_datetime(M[dc]); M = M.sort_values(dc).set_index(dc)
    o = M.resample(TF).agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
    return o

def add_indicators(df):
    df = df.copy()
    hi, lo, cl = df['high'], df['low'], df['close']
    tr = pd.concat([(hi-lo),(hi-cl.shift()).abs(),(lo-cl.shift()).abs()],axis=1).max(axis=1)
    df['atr'] = tr.ewm(alpha=1/ATR_N, adjust=False, min_periods=ATR_N).mean()
    df['don_hi'] = hi.rolling(LOOKBACK).max().shift(1)   # 前 N 根高點（不含當根）
    df['don_lo'] = lo.rolling(LOOKBACK).min().shift(1)
    df['brk_up']  = cl > df['don_hi']
    df['brk_dn']  = cl < df['don_lo']
    df['ret_1']   = cl.pct_change()*100
    df['ret_12']  = cl.pct_change(12)*100   # 1 小時
    df['ret_48']  = cl.pct_change(48)*100   # 4 小時
    # 突破幅度（相對 ATR）
    df['brk_strength_up'] = (cl - df['don_hi'])/df['atr']
    df['brk_strength_dn'] = (df['don_lo'] - cl)/df['atr']
    return df

def backtest(df, signals, stop_atr=STOP_ATR, target_atr=TARGET_ATR, max_hold=MAX_HOLD):
    """signals: list of (bar_index, direction) — direction +1 long / -1 short
    進場用訊號次根的 open，出場用 ATR 停損/停利/時間到。"""
    o=df['open'].values; h=df['high'].values; l=df['low'].values; c=df['close'].values
    atr=df['atr'].values
    n=len(df)
    trades=[]; busy_until=-1
    for idx, d in signals:
        if idx <= busy_until or idx+1 >= n or np.isnan(atr[idx]): continue
        e = idx+1
        entry = o[e]
        a = atr[idx]
        stop = entry - d*stop_atr*a
        tgt  = entry + d*target_atr*a
        exit_px=None; exit_i=None; reason=None
        for j in range(e, min(e+max_hold, n)):
            if d>0:
                if l[j] <= stop: exit_px, exit_i, reason = stop, j, 'stop'; break
                if h[j] >= tgt:  exit_px, exit_i, reason = tgt,  j, 'target'; break
            else:
                if h[j] >= stop: exit_px, exit_i, reason = stop, j, 'stop'; break
                if l[j] <= tgt:  exit_px, exit_i, reason = tgt,  j, 'target'; break
        if exit_px is None:
            exit_i = min(e+max_hold-1, n-1); exit_px = c[exit_i]; reason='time'
        gross = d*(exit_px-entry)
        fees = (entry+exit_px)*FEE
        trades.append({'entry_i':e,'exit_i':exit_i,'dir':d,'entry':entry,'exit':exit_px,
                       'pnl':gross-fees,'reason':reason,'bars':exit_i-e})
        busy_until = exit_i
    return pd.DataFrame(trades)

if __name__ == '__main__':
    print(f"=== 5m 突破策略基線（{TF}, Donchian {LOOKBACK}, ATR stop {STOP_ATR} / target {TARGET_ATR}）===\n")
    assets = [('BTC','/root/gridlab/btc_1m.parquet')]
    for name, path in assets:
        df = load_5m(path, name)
        df = add_indicators(df)
        n_sig = int(df['brk_up'].sum() + df['brk_dn'].sum())
        span = f"{df.index[0]} ~ {df.index[-1]}"
        print(f"{name}: {len(df):,} 根 5m  ({span})")
        print(f"  突破訊號: {n_sig} 個（多 {int(df['brk_up'].sum())} / 空 {int(df['brk_dn'].sum())}）")
        print(f"  → 每次訊號問一次 Jev: {n_sig} 次呼叫 ≈ {n_sig*0.35/60:.1f} 分鐘, "
              f"${n_sig*358/1e6*0.042:.4f}")

        sigs = [(i, 1) for i in np.where(df['brk_up'].values)[0]] + \
               [(i, -1) for i in np.where(df['brk_dn'].values)[0]]
        sigs.sort()
        T = backtest(df, sigs)
        if len(T)==0: print("  無交易"); continue
        print(f"\n  純規則（全收）: {len(T)} 筆")
        print(f"    總PnL {T['pnl'].sum():+.2f}  勝率 {(T['pnl']>0).mean():.1%}  "
              f"平均 {T['pnl'].mean():+.3f}  最大單筆虧損 {T['pnl'].min():+.2f}")
        print(f"    出場原因: {T['reason'].value_counts().to_dict()}")
        print(f"    平均持倉 {T['bars'].mean():.1f} 根 (= {T['bars'].mean()*5/60:.1f} 小時)")
        print(f"    多單 {int((T['dir']>0).sum())} / 空單 {int((T['dir']<0).sum())}")

        # 基準對照：隨機進場（同筆數）
        rng = np.random.default_rng(42)
        rnd_idx = rng.choice(np.arange(LOOKBACK+ATR_N, len(df)-MAX_HOLD-2), size=len(T), replace=False)
        rnd_sigs = [(int(i), int(rng.choice([1,-1]))) for i in rnd_idx]
        rnd_sigs.sort()
        TR = backtest(df, rnd_sigs)
        print(f"\n  隨機進場對照（{len(TR)} 筆）: 總PnL {TR['pnl'].sum():+.2f}  "
              f"勝率 {(TR['pnl']>0).mean():.1%}")
        T.to_csv('/tmp/breakout_rule_trades.csv', index=False)
        df[['open','high','low','close','atr','don_hi','don_lo','brk_up','brk_dn',
            'ret_1','ret_12','ret_48','brk_strength_up','brk_strength_dn']].to_parquet('/tmp/btc_5m.parquet')
        print(f"\n  已存 /tmp/breakout_rule_trades.csv 與 /tmp/btc_5m.parquet")
