#!/usr/bin/env python3
"""Stage 7b：1h 突破策略驗證（同 4h 的嚴格協定）。

1h 資料：okx_data_5m 重採樣（443 天，8 個標的）
IS 前 50% / VAL 50-75% / TEST 75-100%（TEST 只跑一次）
"""
import json
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, "/root/Crypto-Backtesting-Lab")
from research.breakout_jev2.lib_breakout import backtest_breakout, metrics, prepare
from research.breakout_jev2.lib_data_multi import (
    BARS_PER_YEAR, available_1h, load_1h_from_5m,
)

OUT = "/root/Crypto-Backtesting-Lab/runtime/breakout_jev2"
EXIT_LOOKBACKS = [12, 24, 48, 96]
SEG = {"IS": (0.00, 0.50), "VAL": (0.50, 0.75), "TEST": (0.75, 1.00)}
GRID = [(lb, d, ex, st, 3.0, el)
        for lb in (24, 48, 96, 192)
        for d in ("long", "both")
        for ex in ("trail", "donchian")
        for st in (1.5, 2.5, 4.0)
        for el in (48, 96)]


def eval_segment(frames, seg, grid):
    out = defaultdict(list)
    for sym, df in frames.items():
        n = len(df)
        s, e = int(n * seg[0]), int(n * seg[1])
        if e - s < 200:
            continue
        for p in grid:
            lb, d, ex, st, tr_, el = p
            tr, eq = backtest_breakout(df, lookback=lb, direction=d, exit_method=ex,
                                       stop_atr=st, target_atr=tr_, trail_atr=tr_,
                                       exit_lookback=el, start=s, end=e)
            m = metrics(tr, eq, e - s, BARS_PER_YEAR["1h"])
            if m["n"] < 10:
                continue
            out[p].append({"sym": sym, **{k: m[k] for k in
                                          ("sharpe", "avg_pct", "n", "maxdd_pct", "pf", "ret_pct")}})
    return out


def summarize(agg):
    rows = []
    for p, rs in agg.items():
        if len(rs) < 4:
            continue
        sh = np.array([r["sharpe"] for r in rs])
        av = np.array([r["avg_pct"] for r in rs])
        rows.append({"params": list(p), "median_sharpe": float(np.median(sh)),
                     "mean_avg_pct": float(av.mean()), "pos_ratio": float((av > 0).mean()),
                     "n_syms": len(rs), "total_n": int(sum(r["n"] for r in rs)), "per": rs})
    rows.sort(key=lambda x: x["median_sharpe"], reverse=True)
    return rows


def main() -> None:
    syms = available_1h()
    frames = {}
    for s in syms:
        try:
            frames[s] = prepare(load_1h_from_5m(s), [24, 48, 96, 192], EXIT_LOOKBACKS)
        except Exception as ex:
            print(f"  [skip] {s}: {ex}")
    print(f"1h 標的 {list(frames)}")
    for s, df in frames.items():
        print(f"  {s:6s} {len(df):,} 根  {df['timestamp'].iloc[0].date()} ~ {df['timestamp'].iloc[-1].date()}")

    print(f"\n候選參數 {len(GRID)} 組")
    is_rows = summarize(eval_segment(frames, SEG["IS"], GRID))
    val_rows = summarize(eval_segment(frames, SEG["VAL"], GRID))
    val_map = {tuple(r["params"]): r for r in val_rows}

    print(f"\nIS 前 10：")
    print(f"{'params':>38}{'medSh':>9}{'pos':>7}{'avg%':>10}")
    for r in is_rows[:10]:
        print(f"{str(tuple(r['params'])):>38}{r['median_sharpe']:>9.2f}"
              f"{r['pos_ratio']:>7.0%}{r['mean_avg_pct']:>10.4f}")

    cands = [r for r in is_rows if tuple(r["params"]) in val_map
             and r["mean_avg_pct"] > 0 and val_map[tuple(r["params"])]["mean_avg_pct"] > 0]
    print(f"\nIS 與 VAL 皆為正的候選：{len(cands)} / {len(is_rows)}")
    print(f"{'params':>38}{'IS medSh':>10}{'IS pos':>8}{'VAL medSh':>11}{'VAL pos':>9}")
    for r in cands[:12]:
        v = val_map[tuple(r["params"])]
        print(f"{str(tuple(r['params'])):>38}{r['median_sharpe']:>10.2f}{r['pos_ratio']:>8.0%}"
              f"{v['median_sharpe']:>11.2f}{v['pos_ratio']:>9.0%}")

    report = {"candidates": cands[:12]}
    if cands:
        # 取「IS+VAL 中位 Sharpe 合計最高」者（先驗承諾的準則，不看 TEST）
        cands.sort(key=lambda r: r["median_sharpe"] + val_map[tuple(r["params"])]["median_sharpe"],
                   reverse=True)
        best = cands[0]
        v = val_map[tuple(best["params"])]
        print(f"\n選定（以 IS+VAL 為準，TEST 未看）：{tuple(best['params'])}")

        test_rows = summarize(eval_segment(frames, SEG["TEST"], [tuple(best["params"])]))
        if test_rows:
            t = test_rows[0]
            print(f"\n=== 1h TEST 段（只跑一次）===")
            print(f"  IS   : 中位 Sharpe {best['median_sharpe']:+.2f}  正標的 {best['pos_ratio']:.0%}  "
                  f"平均 {best['mean_avg_pct']:+.4f}%/筆")
            print(f"  VAL  : 中位 Sharpe {v['median_sharpe']:+.2f}  正標的 {v['pos_ratio']:.0%}  "
                  f"平均 {v['mean_avg_pct']:+.4f}%/筆")
            print(f"  TEST : 中位 Sharpe {t['median_sharpe']:+.2f}  正標的 {t['pos_ratio']:.0%}  "
                  f"平均 {t['mean_avg_pct']:+.4f}%/筆  總交易 {t['total_n']}")
            print(f"  TEST 各標的:")
            for r in sorted(t["per"], key=lambda x: -x["sharpe"]):
                print(f"    {r['sym']:6s} Sharpe {r['sharpe']:+6.2f}  平均 {r['avg_pct']:+.4f}%  "
                      f"n={r['n']:>4}  MaxDD {r['maxdd_pct']:+7.1f}%  PF {r['pf']:5.2f}  "
                      f"總報酬 {r['ret_pct']:+.1f}%")
            report["best"] = {"params": best["params"], "IS": best, "VAL": v, "TEST": t}

    json.dump(report, open(f"{OUT}/s7_validate_1h.json", "w"), indent=2)
    print(f"\n-> {OUT}/s7_validate_1h.json")


if __name__ == "__main__":
    main()
