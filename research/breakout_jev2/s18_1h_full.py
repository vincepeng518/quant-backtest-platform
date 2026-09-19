#!/usr/bin/env python3
"""Stage 18：用完整 1h 資料重測（修補統計力缺口）。

背景：先前 1h 的結論（Stage 7b：IS +0.70 → TEST −2.35）建立在
**只有 443 天、8 檔**的資料上。對一個年交易約 200 次的策略，
這等於只有 ~1.2 年的有效樣本，統計力嚴重不足。

本階段用 okx_data 的 23,041 根 × 11 檔（2.6 年）重測——是先前樣本的 2.2 倍。

並且**內建 Stage 17 的教訓**：一開始就做留出期切點掃描，
不只看單一切點。（Stage 17 證明單一切點的結論可能是切點運氣。）
"""
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/root/Crypto-Backtesting-Lab")
from research.breakout_jev2.lib_breakout import backtest_breakout, metrics, prepare
from research.breakout_jev2.lib_data_multi import (BARS_PER_YEAR, available_1h_long,
                                                   load_1h_long)

OUT = "/root/Crypto-Backtesting-Lab/runtime/breakout_jev2"
EXIT_LOOKBACKS = [12, 24, 48, 96]
LBS = [24, 48, 96, 192]
BPY = BARS_PER_YEAR["1h"]
CFGS = [(lb, "both", ex, st, tr, el)
        for ex in ("oco", "trail", "donchian", "trail_both")
        for lb, st, tr, el in [(96, 4.0, 3.0, 96), (48, 3.0, 2.0, 48)]]


def ev(df, cfg, start, end):
    lb, d, ex, st, tr, el = cfg
    t, eq = backtest_breakout(df, lookback=lb, direction=d, exit_method=ex,
                              stop_atr=st, target_atr=tr, trail_atr=tr,
                              exit_lookback=el, start=start, end=end)
    return metrics(t, eq, end - start, BPY)


def main() -> None:
    syms = available_1h_long()
    frames = {}
    for s in syms:
        try:
            frames[s] = prepare(load_1h_long(s), LBS, EXIT_LOOKBACKS)
        except Exception as e:
            print(f"  skip {s}: {e}")
    print("=" * 96)
    print(f"Stage 18：完整 1h 重測（{len(frames)} 檔 × ~23,041 根 = 2.6 年）")
    print("=" * 96)
    lens = sorted(len(v) for v in frames.values())
    print(f"根數範圍 {lens[0]:,} ~ {lens[-1]:,}  年數 {(lens[-1] / BPY):.2f}")

    # ── 開發期掃描 ──
    print(f"\n{'配置':>24}{'中位Sharpe':>12}{'正標的':>9}{'平均%':>10}{'總交易':>8}")
    dev = {}
    for cfg in CFGS:
        per = []
        for s, df in frames.items():
            n = len(df)
            cut = int(n * 0.6)
            m = ev(df, cfg, 0, cut)
            if m["n"] >= 3:
                per.append((m["sharpe"], m["avg_pct"], m["n"]))
        if len(per) < 5:
            continue
        sh = np.array([x[0] for x in per])
        av = np.array([x[1] for x in per])
        lbl = f"lb{cfg[0]}_{cfg[2]}_st{cfg[3]:.0f}"
        dev[lbl] = {"cfg": cfg, "median_sharpe": float(np.median(sh)),
                    "pos_ratio": float((av > 0).mean()), "mean_avg_pct": float(av.mean()),
                    "total_n": int(sum(x[2] for x in per))}
        print(f"{lbl:>24}{np.median(sh):>12.2f}{(av > 0).mean():>9.0%}"
              f"{av.mean():>10.4f}{sum(x[2] for x in per):>8}")

    # ── 選最佳（依開發期）──
    cands = [(k, v) for k, v in dev.items() if v["median_sharpe"] > 0.2 and v["pos_ratio"] >= 0.6]
    cands.sort(key=lambda kv: -kv[1]["median_sharpe"])
    if not cands:
        print("\n開發期無候選 → 停止")
        json.dump({"dev": dev, "verdict": "no_dev_candidate"},
                  open(f"{OUT}/s18_1h_full.json", "w"), indent=2)
        return

    bestk, bestv = cands[0]
    cfg = bestv["cfg"]
    print(f"\n選定（依開發期）：{bestk}  中位Sharpe {bestv['median_sharpe']:+.2f}  "
          f"正標的 {bestv['pos_ratio']:.0%}")

    # ── 留出期切點掃描（Stage 17 教訓：內建）──
    print("\n" + "=" * 96)
    print("留出期切點掃描（同一策略/參數，只改切點）")
    print("=" * 96)
    print(f"{'切點':>7}{'中位Sharpe':>12}{'正標的':>9}{'平均%':>10}{'總交易':>8}")
    sweep = []
    for frac in np.arange(0.50, 0.91, 0.05):
        per = []
        for s, df in frames.items():
            n = len(df)
            cut = int(n * frac)
            if n - cut < 200:
                continue
            m = ev(df, cfg, cut, n)
            if m["n"] >= 2:
                per.append((m["sharpe"], m["avg_pct"], m["n"]))
        if len(per) < 5:
            continue
        sh = np.array([x[0] for x in per])
        av = np.array([x[1] for x in per])
        sweep.append({"frac": float(frac), "median_sharpe": float(np.median(sh)),
                      "pos_ratio": float((av > 0).mean()), "mean_avg_pct": float(av.mean()),
                      "n_trades": int(sum(x[2] for x in per))})
        print(f"{frac:>7.2f}{np.median(sh):>12.2f}{(av > 0).mean():>9.0%}"
              f"{av.mean():>10.4f}{sum(x[2] for x in per):>8}")

    if sweep:
        ms = np.array([x["median_sharpe"] for x in sweep])
        pr = np.array([x["pos_ratio"] for x in sweep])
        n_strong = int(((ms > 0.3) & (pr >= 0.6)).sum())
        print(f"\n彙總：中位 Sharpe 範圍 [{ms.min():+.2f}, {ms.max():+.2f}]  "
              f"平均 {ms.mean():+.2f}  標準差 {ms.std():.2f}")
        print(f"      正標的範圍 [{pr.min():.0%}, {pr.max():.0%}]")
        print(f"      通過門檻的切點 {n_strong}/{len(sweep)}")
        if n_strong >= len(sweep) * 0.7:
            print("  → **穩健 ✓** 多數切點通過")
        else:
            print("  → **不穩健 ✗** 結果取決於切點；1h 同樣沒有可證實的 edge")

    json.dump({"dev": dev, "best": bestk, "sweep": sweep},
              open(f"{OUT}/s18_1h_full.json", "w"), indent=2)
    print(f"\n-> {OUT}/s18_1h_full.json")


if __name__ == "__main__":
    main()
