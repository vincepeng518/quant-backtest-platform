#!/usr/bin/env python3
"""Stage 17：留出期切點敏感度（決定性檢定）。

Stage 16 發現：同一策略、同資料、同參數，只改「留出期起點」，
中位 Sharpe 就從 +0.06 變到 +0.30。這說明結論取決於切點選擇，不是穩健 edge。

本階段做完整掃描：把留出期起點從 50% 掃到 90%（每 5% 一格），
每一格算留出期的中位 Sharpe 與正標的比率。
  → 若結果在多數切點上為正 → 穩健
  → 若隨切點大幅變動、且跨越零 → 不穩健，先前的正結果是切點運氣
"""
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/root/Crypto-Backtesting-Lab")
from research.breakout_jev2.lib_breakout import backtest_breakout, metrics, prepare
from research.breakout_jev2.lib_data_multi import BARS_PER_YEAR, load_4h

OUT = "/root/Crypto-Backtesting-Lab/runtime/breakout_jev2"
EXIT_LOOKBACKS = [12, 24, 48, 96]
LBS = [24, 48, 96, 192]
SYMS4 = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT", "XRPUSDT"]
CFG = (96, "both", "donchian", 4.0, 3.0, 96)
lb, d, ex, st, tr_, el = CFG


def main() -> None:
    frames = {}
    for sym in SYMS4:
        try:
            frames[sym] = prepare(load_4h(sym, "long"), LBS, EXIT_LOOKBACKS)
        except FileNotFoundError:
            continue
    print("=" * 94)
    print("留出期切點敏感度掃描（同一策略/參數，只改切點）")
    print("=" * 94)
    print(f"{'切點比例':>10}{'留出起點':>14}{'中位Sharpe':>12}{'正標的':>9}"
          f"{'平均%':>10}{'總交易':>8}{'各檔 Sharpe':>28}")

    rows = []
    for frac in np.arange(0.50, 0.91, 0.05):
        per = []
        for sym, df in frames.items():
            n = len(df)
            cut = int(n * frac)
            if n - cut < 200:
                continue
            t, eq = backtest_breakout(df, lookback=lb, direction=d, exit_method=ex,
                                      stop_atr=st, target_atr=tr_, trail_atr=tr_,
                                      exit_lookback=el, start=cut, end=n)
            m = metrics(t, eq, n - cut, BARS_PER_YEAR["4h"])
            if m["n"] < 2:
                continue
            per.append({"sym": sym, "sharpe": m["sharpe"], "avg_pct": m["avg_pct"],
                        "n": m["n"], "cut_date": str(pd.Timestamp(
                            df["timestamp"].iloc[cut]))[:10]})
        if len(per) < 4:
            continue
        sh = np.array([x["sharpe"] for x in per])
        av = np.array([x["avg_pct"] for x in per])
        sh_str = " ".join(f"{x['sharpe']:+.1f}" for x in per)
        print(f"{frac:>10.2f}{per[0]['cut_date']:>14}{np.median(sh):>12.2f}"
              f"{np.mean(av > 0):>9.0%}{av.mean():>10.4f}{sum(x['n'] for x in per):>8}"
              f"{sh_str:>28}")
        rows.append({"frac": float(frac), "cut_date": per[0]["cut_date"],
                     "median_sharpe": float(np.median(sh)), "pos_ratio": float(np.mean(av > 0)),
                     "mean_avg_pct": float(av.mean()), "n_trades": int(sum(x["n"] for x in per)),
                     "per": per})

    if not rows:
        print("無資料")
        return
    ms = np.array([r["median_sharpe"] for r in rows])
    pr = np.array([r["pos_ratio"] for r in rows])
    print(f"\n{'=' * 94}\n彙總\n{'=' * 94}")
    print(f"  切點數: {len(rows)}")
    print(f"  中位 Sharpe: 範圍 [{ms.min():+.2f}, {ms.max():+.2f}]  "
          f"平均 {ms.mean():+.2f}  標準差 {ms.std():.2f}")
    print(f"  正標的比率: 範圍 [{pr.min():.0%}, {pr.max():.0%}]  平均 {pr.mean():.0%}")
    n_pos = int((ms > 0).sum())
    print(f"  中位 Sharpe > 0 的切點: {n_pos}/{len(rows)}")
    n_strong = int(((ms > 0.3) & (pr >= 0.6)).sum())
    print(f"  同時『中位 Shar>0.3 且 正標的>=60%』的切點: {n_strong}/{len(rows)}")
    print()
    if n_strong >= len(rows) * 0.7:
        print("  → 穩健：多數切點都能通過 ✓")
    else:
        print("  → **不穩健 ✗**：結果高度取決於切點選擇。")
        print("     先前看到的正結果是『切點運氣』，不是可交易的 edge。")
        print(f"     （Stage 15 用的是 frac=0.60 → Sharpe {[r for r in rows if abs(r['frac']-0.60)<1e-9][0]['median_sharpe']:+.2f}，"
              f"而 frac=0.75 只有 {[r for r in rows if abs(r['frac']-0.75)<1e-9][0]['median_sharpe']:+.2f}）")

    json.dump(rows, open(f"{OUT}/s17_split_sensitivity.json", "w"), indent=2)
    print(f"\n-> {OUT}/s17_split_sensitivity.json")


if __name__ == "__main__":
    main()
