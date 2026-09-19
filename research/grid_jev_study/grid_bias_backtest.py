#!/usr/bin/env python3
"""Grid+Jev 方向偏置回測：Jev regime vs 規則 regime vs 純中性。

用真實 grid_core 逐分鐘撮合。三組對照（gate 全部沿用已驗證規則）：
  A. 純中性      regime 永遠 0
  B. 規則方向    SMA50/SMA200 + ADX>=25 + |DI差|>4
  C. Jev 方向    每 REBALANCE_DAYS 問一次 Jev

同一份資料、同一組 gate、同一組網格參數 → 只差方向來源。
"""
import sys, os, os, json, time
sys.path.insert(0, '/root/Crypto-Backtesting-Lab')
import numpy as np, pandas as pd

from engine.grid_core import GridState
from engine.strategies.grid_switcher import compute_indicators, NATR_Q, MIN_HIST
from engine.strategies.grid_jev_bias import jev_direction, P_BIAS, CONF_MIN

API_KEY = os.getenv("AI_GATEWAY_API_KEY") or \
    os.environ.get("AI_GATEWAY_API_KEY", "")

M = pd.read_parquet('/root/gridlab/btc_1m.parquet')
dc = [c for c in M.columns if c.lower() in ('dt','timestamp','time','date')][0]
M[dc] = pd.to_datetime(M[dc]); M = M.sort_values(dc).reset_index(drop=True)
M = M.set_index(dc)

# 日線 + 指標
day = M.resample('1D').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna().reset_index()
day.columns = ['date','open','high','low','close']
day = compute_indicators(day)
day['ret_5d'] = day['close'].pct_change(5)*100
day['ret_14d'] = day['close'].pct_change(14)*100
day['ret_30d'] = day['close'].pct_change(30)*100
print(f"日線 {len(day)} 根，nATR 門檻生效 {day['natr_thr'].notna().sum()} 根")

# ── 用真實 grid_core 跑一個視窗 ──
def run_window(start_ts, regime_fn, days=30, hr_mult=16.0, n_grids=80, qty=0.0023):
    """regime_fn(bar_index_in_window, ts) -> -1/0/1"""
    end = start_ts + pd.Timedelta(days=days)
    seg = M.loc[(M.index >= start_ts) & (M.index < end)]
    if len(seg) < 5000: return None
    i0 = day.index[day['date'] <= start_ts]
    if len(i0) == 0: return None
    row = day.loc[i0[-1]]
    if pd.isna(row['atr']) or pd.isna(row['natr_thr']): return None
    if float(row['natr']) < float(row['natr_thr']):
        return {'pnl': 0.0, 'gated': False, 'regime': 0, 'n_trades': 0}
    hr = float(row['atr']) * hr_mult
    o = seg['open'].values.astype(float); h = seg['high'].values.astype(float)
    l = seg['low'].values.astype(float); c = seg['close'].values.astype(float)
    ts_idx = seg.index
    g = GridState(n_grids=n_grids, qty=qty, fee_bps=1.0, taker_bps=3.0,
                  recenter_gap=hr/3.0, cap_btc=0.20, regime=0)
    g.build(o[0], hr)
    for i in range(len(c)):
        g.regime = regime_fn(i, ts_idx[i])
        g.on_bar(o[i], h[i], l[i], c[i])
        g.settle(c[i], funding_rate_8h=0.0, minutes=1.0, next_half_range=hr)
    return {'pnl': float(g.equity(c[-1])), 'gated': True, 'regime': g.regime,
            'n_trades': g.n_trades}

# ── 視窗清單 ──
t0 = day['date'].iloc[MIN_HIST]
t_end = day['date'].iloc[-1] - pd.Timedelta(days=31)
wins, ts = [], t0
while ts <= t_end:
    wins.append(ts); ts += pd.Timedelta(days=5)
print(f"候選視窗 {len(wins)} 個")

# ── Jev 方向：每個視窗問一次（快取）──
CACHE = '/root/Crypto-Backtesting-Lab/runtime/grid_jev_backtest_cache.json'
cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}

def jev_regime_for(start_ts, row):
    key = f"{start_ts.date()}"
    if key in cache: return cache[key]
    state = {"asset":"BTC/USDT","timeframe":"daily",
             "close":round(float(row['close']),1),"atr_14d":round(float(row['atr']),1),
             "natr":round(float(row['natr']),4),
             "natr_historical_median":round(float(row['natr_thr']),4),
             "adx":round(float(row['adx']),1),
             "plus_di":round(float(row['plus_di']),1),
             "minus_di":round(float(row['minus_di']),1),
             "sma50":round(float(row['sma50']),1) if not pd.isna(row['sma50']) else None,
             "sma200":round(float(row['sma200']),1) if not pd.isna(row['sma200']) else None,
             "return_5d_pct":round(float(row['ret_5d']),2) if not pd.isna(row['ret_5d']) else None,
             "return_14d_pct":round(float(row['ret_14d']),2) if not pd.isna(row['ret_14d']) else None,
             "return_30d_pct":round(float(row['ret_30d']),2) if not pd.isna(row['ret_30d']) else None}
    res = jev_direction(state, API_KEY)
    cache[key] = res; json.dump(cache, open(CACHE,'w'))
    return res

# 規則方向
def rule_regime(row, adx_trend=25.0, di_diff=4.0):
    if pd.isna(row['sma200']): return 0
    if row['sma50'] > row['sma200'] and row['adx'] >= adx_trend and (row['plus_di']-row['minus_di']) > di_diff:
        return 1
    if row['sma50'] < row['sma200'] and row['adx'] >= adx_trend and (row['minus_di']-row['plus_di']) > di_diff:
        return -1
    return 0

print("\n=== 開始回測（三組對照）===", flush=True)
rows=[]
for j, t in enumerate(wins):
    i0 = day.index[day['date'] <= t]
    if len(i0) == 0: continue
    row = day.loc[i0[-1]]
    if pd.isna(row['natr_thr']): continue

    # A 純中性
    ra = run_window(t, lambda i, ts: 0)
    if ra is None: continue
    # B 規則方向
    rr = rule_regime(row)
    rb = run_window(t, lambda i, ts, rr=rr: rr)
    # C Jev 方向
    jr = jev_regime_for(t, row)
    rc = run_window(t, lambda i, ts, jr=jr: jr['regime'])

    seg = M.loc[(M.index>=t)&(M.index<t+pd.Timedelta(days=30))]['close']
    rows.append({'start':t,'gated':ra['gated'],'natr':float(row['natr']),
                 'natr_thr':float(row['natr_thr']),'adx':float(row['adx']),
                 'rule_regime':rr,'jev_regime':jr['regime'],
                 'jev_p_up':jr.get('p_up'),'jev_p_down':jr.get('p_down'),
                 'jev_conf':jr.get('confidence'),
                 'pnl_neutral':ra['pnl'],'pnl_rule':rb['pnl'] if rb else None,
                 'pnl_jev':rc['pnl'] if rc else None,
                 'fwd_disp_pct':abs(seg.iloc[-1]-seg.iloc[0])/seg.iloc[0]*100 if len(seg)>1 else None})
    if (j+1)%10==0: print(f"  {j+1}/{len(wins)}…", flush=True)

S=pd.DataFrame(rows)
S.to_csv('/tmp/grid_jev_bias_backtest.csv', index=False)
tok=sum(v.get('tokens',0) for v in cache.values()) if cache else 0
print(f"\n完成 {len(S)} 視窗，Jev 呼叫 {len(cache)} 次 / {tok} token = ${tok/1e6*0.042:.5f}")

g = S[S['gated']]
print(f"\n=== gate 過的 {len(g)} 個視窗 ===")
for nm, col in [('純中性','pnl_neutral'),('規則方向','pnl_rule'),('Jev 方向','pnl_jev')]:
    v = g[col].dropna()
    if len(v)==0: continue
    print(f"{nm:10s} 總PnL {v.sum():>9.1f}  平均 {v.mean():>8.1f}  最低 {v.min():>8.1f}  "
          f"勝率 {(v>0).mean():>6.1%}")

print(f"\n=== 方向分布 ===")
print(f"規則: {g['rule_regime'].value_counts().to_dict()}")
print(f"Jev : {g['jev_regime'].value_counts().to_dict()}")

print(f"\n=== gate 全體（含 flat 的 0）===")
for nm,col in [('純中性','pnl_neutral'),('規則方向','pnl_rule'),('Jev 方向','pnl_jev')]:
    v=S[col].dropna()
    print(f"{nm:10s} 總PnL {v.sum():>9.1f}")
