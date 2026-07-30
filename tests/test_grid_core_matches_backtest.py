"""斷言 GridState (逐 tick, 模擬倉用) 與 grid2.run_grid2 (向量化回測) 數字完全一致。

如果這個測試掛了, 代表模擬倉的撮合已經跟回測發散 —— 模擬倉結果不可信。
跑法:
    cd /root/Crypto-Backtesting-Lab && ./venv/bin/python tests/test_grid_core_matches_backtest.py
"""
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "/root/Crypto-Backtesting-Lab")
sys.path.insert(0, "/root/gridlab")

from engine.grid_core import GridState
from grid2 import run_grid2


def replay(df, active, regime, hr_arr, *, n_grids=80, qty=0.0023,
           fee_bps=1.0, taker_bps=3.0, recenter_gap=1000.0,
           cap_btc=0.20, funding_rate_8h=0.0):
    """用 GridState 逐根 K 線重放, 回傳與 run_grid2 相同的統計。"""
    o = df["open"].to_numpy(float); h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float);  c = df["close"].to_numpy(float)
    n = len(df)

    g = GridState(n_grids=n_grids, qty=qty, fee_bps=fee_bps, taker_bps=taker_bps,
                  recenter_gap=recenter_gap, cap_btc=cap_btc)
    equity = np.empty(n); posarr = np.empty(n)
    was_active = True

    for i in range(n):
        act = True if active is None else bool(active[i])
        if not act:
            g.flatten(o[i])
            was_active = False
            equity[i] = g.cash; posarr[i] = 0.0
            continue
        if not was_active:
            g.build(o[i], float(hr_arr[i]))
            was_active = True
        elif not g.armed:                      # 第一根
            g.build(o[i], float(hr_arr[i]))

        g.regime = 0 if regime is None else int(regime[i])
        g.on_bar(o[i], h[i], l[i], c[i])
        eq = g.settle(c[i], funding_rate_8h=funding_rate_8h, minutes=1.0,
                      next_half_range=float(hr_arr[i]))
        equity[i] = eq; posarr[i] = g.pos

    eqs = pd.Series(equity, index=df["dt"].values)
    dd = eqs - eqs.cummax()
    return dict(pnl=float(equity[-1]), max_dd=float(dd.min()),
                trades=g.n_trades, recenters=g.n_recenter, flattens=g.n_flat,
                fees=g.fees_paid, funding=g.funding_paid,
                max_abs_pos_btc=float(np.max(np.abs(posarr))))


def main():
    import engine.strategies.grid_switcher as gs

    d = gs.compute_indicators(gs.load_data())
    modes, hrs = [], []
    for i in range(len(d)):
        if pd.isna(d["adx"].iloc[i]):
            modes.append("flat"); hrs.append(np.nan); continue
        s = gs.decide(d, i)
        modes.append(s.mode); hrs.append(s.geometry["half_range"])
    d["mode"] = modes; d["hr"] = hrs
    dd = d.set_index(pd.to_datetime(d["date"]))

    m1 = pd.read_parquet("/root/gridlab/btc_1m.parquet").reset_index(drop=True)
    day = m1["dt"].dt.floor("D")
    mm = day.map(dd["mode"].shift(1)).fillna("flat")
    hr = day.map(dd["hr"].shift(1)).ffill().bfill().to_numpy()
    active = mm.ne("flat").to_numpy()
    regime = np.where(mm.eq("long"), 1, np.where(mm.eq("short"), -1, 0)).astype(int)

    CFG = dict(n_grids=80, qty=0.0023, recenter_gap=1000, fee_bps=1.0)

    failures = 0
    for fr in (0.0, 0.0001):
        ref = run_grid2(m1, half_range=3000, cap_btc=0.20, active=active,
                        regime=regime, half_range_arr=hr,
                        funding_rate_8h=fr, **CFG)
        got = replay(m1, active, regime, hr, cap_btc=0.20,
                     funding_rate_8h=fr, **CFG)
        print(f"\n--- funding {fr*100:.2f}%/8h ---")
        for k in ("pnl", "max_dd", "trades", "recenters", "flattens",
                  "fees", "funding", "max_abs_pos_btc"):
            a, b = ref[k], got[k]
            ok = (abs(a - b) < 1e-6) if isinstance(a, float) else (a == b)
            if not ok:
                failures += 1
            print(f"  {'OK ' if ok else 'FAIL'} {k:18s} backtest={a!r:>22} core={b!r:>22}")

    print()
    if failures:
        print(f"FAILED: {failures} 項不一致 — 模擬倉撮合已與回測發散, 不可上線")
        return 1
    print("PASS: GridState 與 run_grid2 完全一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
