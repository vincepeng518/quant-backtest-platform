#!/usr/bin/env python3
"""Stage 8：完整診斷——排除「選參數選壞了」的可能，並檢驗 regime 依賴與組合層面。

要回答的問題：
  1. 4h 的 25 組 / 1h 的 96 組，**全部**的 TEST 分布如何？（不是挑最好的，是看整體）
     若中位數 ≈ 0 且無穩定為正者 → 沒有 edge，不是我選壞了
  2. **組合層面**（7 檔等權）是否比單標的中位數好？（趨勢跟隨以組合分散著稱）
  3. **逐年表現**——是否 regime 依賴（2018-2021 大牛市 vs 之後）
  4. **1d**（從未用過的資料）是否不同
"""
import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, "/root/Crypto-Backtesting-Lab")
from research.breakout_jev2.lib_breakout import backtest_breakout, metrics, prepare
from research.breakout_jev2.lib_data_multi import (
    BARS_PER_YEAR, available_1h, load_1d, load_1h_from_5m, load_4h,
)

OUT = "/root/Crypto-Backtesting-Lab/runtime/breakout_jev2"
EXIT_LOOKBACKS = [12, 24, 48, 96]
LBS = [24, 48, 96, 192]
GRID = [(lb, d, ex, st, 3.0, el)
        for lb in LBS for d in ("long", "both")
        for ex in ("trail", "donchian", "oco")
        for st in (1.5, 2.5, 4.0) for el in (24, 48, 96)]
SYMS4 = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT", "XRPUSDT"]
SYM2TAG = {s: s.replace("USDT", "") for s in SYMS4}


def frames_4h():
    out = {}
    for s in SYMS4:
        try:
            out[s] = prepare(load_4h(s, "long"), LBS, EXIT_LOOKBACKS)
        except FileNotFoundError:
            pass
    return out


def run(df, p, bars_per_year, s, e):
    lb, d, ex, st, tr_, el = p
    tr, eq = backtest_breakout(df, lookback=lb, direction=d, exit_method=ex,
                               stop_atr=st, target_atr=tr_, trail_atr=tr_,
                               exit_lookback=el, start=s, end=e)
    return tr, eq, metrics(tr, eq, e - s, bars_per_year)


def main() -> None:
    report = {}
    F4 = frames_4h()
    F1 = {s: prepare(load_1h_from_5m(s), LBS, EXIT_LOOKBACKS) for s in available_1h()}

    # ══════ 1. 全網格 TEST 分布（不看挑選，看整體）══════
    print("=" * 88)
    print("1. 全參數網格的 TEST 段分布（不是挑最好的，是看整體是否有人活著）")
    print("=" * 88)
    for label, F, seg, bpy in [
        ("4h  TEST=2024-2026", F4, (0.75, 1.00), BARS_PER_YEAR["4h"]),
        ("1h  TEST=75-100%", F1, (0.75, 1.00), BARS_PER_YEAR["1h"]),
    ]:
        combos = []
        for p in GRID:
            per = []
            for sym, df in F.items():
                n = len(df)
                s, e = int(n * seg[0]), int(n * seg[1])
                if e - s < 200:
                    continue
                tr, eq, m = run(df, p, bpy, s, e)
                if m["n"] < 5:
                    continue
                per.append({"sym": sym, **{k: m[k] for k in ("sharpe", "avg_pct", "ret_pct", "n")}})
            if len(per) < 4:
                continue
            sh = np.array([x["sharpe"] for x in per])
            av = np.array([x["avg_pct"] for x in per])
            combos.append({"params": list(p), "median_sharpe": float(np.median(sh)),
                           "pos_ratio": float((av > 0).mean()),
                           "mean_avg_pct": float(av.mean()), "n_combos_syms": len(per)})
        if not combos:
            print(f"{label}: 無有效組合")
            continue
        med = np.array([c["median_sharpe"] for c in combos])
        pos = np.array([c["pos_ratio"] for c in combos])
        robust = [c for c in combos if c["median_sharpe"] > 0.3 and c["pos_ratio"] >= 0.6]
        print(f"\n{label}:  有效組合 {len(combos)}")
        print(f"  中位 Sharpe 分布:  p10 {np.percentile(med, 10):+.2f}  "
              f"p50 {np.median(med):+.2f}  p90 {np.percentile(med, 90):+.2f}  "
              f"max {med.max():+.2f}")
        print(f"  正標的比率分布:    p10 {np.percentile(pos, 10):.0%}  "
              f"p50 {np.median(pos):.0%}  max {pos.max():.0%}")
        print(f"  同時滿足『中位 Sharpe>0.3 且 ≥60% 標的正』的組合數: {len(robust)} / {len(combos)}")
        report[label] = {"n_combos": len(combos), "median_sharpe_p50": float(np.median(med)),
                         "median_sharpe_max": float(med.max()),
                         "pos_ratio_p50": float(np.median(pos)),
                         "robust_count": len(robust), "combos": combos}

    # ══════ 2. 組合層面（等權 7 檔）══════
    print("\n" + "=" * 88)
    print("2. 組合層面：7 檔等權，逐年/逐段")
    print("=" * 88)
    for label, F, bpy in [("4h", F4, BARS_PER_YEAR["4h"]), ("1h", F1, BARS_PER_YEAR["1h"])]:
        for p in [(96, "both", "donchian", 4.0, 3.0, 96),
                  (192, "both", "trail", 2.5, 3.0, 48),
                  (48, "both", "trail", 2.5, 3.0, 48)]:
            agg = []
            for sym, df in F.items():
                tr, eq, m = run(df, p, bpy, 0, len(df))
                if m["n"] > 0:
                    agg.append(m)
            if len(agg) < 4:
                continue
            tot_n = sum(m["n"] for m in agg)
            ew = np.mean([m["avg_pct"] for m in agg])
            print(f"  {label} {str(p):>40}  組合等權平均 {ew:+.4f}%/筆  "
                  f"各標的平均數 {np.mean([m['avg_pct'] for m in agg]):+.4f}%  "
                  f"正標的 {np.mean([m['avg_pct']>0 for m in agg]):.0%}  總交易 {tot_n}")

    # ══════ 3. 逐年（regime 依賴）══════
    print("\n" + "=" * 88)
    print("3. 逐年表現（4h，參數=(96,both,donchian,4.0,3.0,96)）—— 檢驗 regime 依賴")
    print("=" * 88)
    P = (96, "both", "donchian", 4.0, 3.0, 96)
    years = defaultdict(lambda: {"avgs": [], "ns": []})
    for sym, df in F4.items():
        yr = df["timestamp"].dt.year.values
        for y in sorted(set(yr)):
            idx = np.where(yr == y)[0]
            if len(idx) < 100:
                continue
            s, e = int(idx[0]), int(idx[-1]) + 1
            tr, eq, m = run(df, P, BARS_PER_YEAR["4h"], s, e)
            if m["n"] < 3:
                continue
            years[y]["avgs"].append(m["avg_pct"])
            years[y]["ns"].append(m["n"])
    print(f"{'年':>6}{'各標的平均%':>14}{'正標的':>9}{'交易數':>8}")
    for y in sorted(years):
        a = np.array(years[y]["avgs"])
        print(f"{y:>6}{a.mean():>14.4f}{np.mean(a > 0):>9.0%}{sum(years[y]['ns']):>8}")
    report["by_year_4h"] = {str(y): {"mean_avg_pct": float(np.mean(years[y]["avgs"])),
                                     "pos_ratio": float(np.mean(np.array(years[y]["avgs"]) > 0)),
                                     "n_trades": int(sum(years[y]["ns"]))}
                            for y in sorted(years)}

    # ══════ 4. 1d（從未用過）══════
    print("\n" + "=" * 88)
    print("4. 1d（bxdata 5 年，從未用於參數選擇）突破檢驗")
    print("=" * 88)
    Fd = {}
    for s in SYMS4:
        try:
            Fd[s] = prepare(load_1d(s), LBS, EXIT_LOOKBACKS)
        except Exception:
            pass
    if Fd:
        for p in [(24, "both", "donchian", 4.0, 3.0, 24), (48, "both", "donchian", 4.0, 3.0, 48),
                  (24, "both", "trail", 2.5, 3.0, 12), (48, "both", "trail", 2.5, 3.0, 24)]:
            per = []
            for sym, df in Fd.items():
                tr, eq, m = run(df, p, BARS_PER_YEAR["1d"], 0, len(df))
                if m["n"] >= 5:
                    per.append(m)
            if len(per) < 4:
                continue
            av = np.array([m["avg_pct"] for m in per])
            sh = np.array([m["sharpe"] for m in per])
            print(f"  {str(p):>40}  平均 {av.mean():+.4f}%  正標的 {np.mean(av>0):.0%}  "
                  f"中位 Sharpe {np.median(sh):+.2f}  總交易 {sum(m['n'] for m in per)}")

    json.dump(report, open(f"{OUT}/s8_diagnostic.json", "w"), indent=2)
    print(f"\n-> {OUT}/s8_diagnostic.json")


if __name__ == "__main__":
    main()
