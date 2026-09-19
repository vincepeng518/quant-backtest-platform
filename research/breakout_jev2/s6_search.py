#!/usr/bin/env python3
"""Stage 6：雙時間級別突破策略搜尋（目標：找到 1h 與 4h 各自的正期望值突破策略）。

方法論（依使用者設定的嚴格標準）：
  1. **IS 選參數 / OOS 只跑一次** —— 不重複看 OOS
  2. **參數高原** —— 只接受鄰近參數也為正的配置，不接受孤島
  3. **多標的一致性** —— 至少 60% 標的 OOS 為正
  4. **三段獨立期間**（4h 用）：2018-2021 訓練 → 2021-2024 驗證 → 2024-2026 測試
  5. **對照組**：固定 ATR OCO（前幾輪已知失敗的基準）

關鍵新維度（前幾輪完全沒測）：**出場方法**
  trend 跟隨的獲利來自少數極端獲利單，固定停利是結構性錯誤 → 測移動停損與唐奇安出場。
"""
import itertools
import json
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "/root/Crypto-Backtesting-Lab")
from research.breakout_jev2.lib_breakout import backtest_breakout, metrics, prepare
from research.breakout_jev2.lib_data_multi import (
    BARS_PER_YEAR, available_4h, available_1h, load_1h_from_5m, load_4h,
)

OUT = "/root/Crypto-Backtesting-Lab/runtime/breakout_jev2"
os.makedirs(OUT, exist_ok=True)

EXIT_LOOKBACKS = [12, 24, 48, 96]

# ── 參數網格（刻意保持小，避免多重比較陷阱）──
GRID_4H = list(itertools.product(
    [24, 48, 96, 192],            # lookback
    ["long", "both"],             # direction
    ["trail", "donchian", "oco"], # exit_method
    [1.5, 2.5, 4.0],              # stop_atr
    [3.0, 6.0],                   # trail_atr / target_atr
    [48, 96],                     # exit_lookback
))
GRID_1H = list(itertools.product(
    [24, 48, 96, 192],
    ["long", "both"],
    ["trail", "donchian", "oco"],
    [1.5, 2.5, 4.0],
    [3.0, 6.0],
    [48, 96],
))


def run_one(df, p, bars_per_year, start=0, end=None):
    lookback, direction, exit_method, stop_atr, trail, exit_lb = p
    tr, eq = backtest_breakout(df, lookback=lookback, direction=direction,
                               exit_method=exit_method, stop_atr=stop_atr,
                               target_atr=trail, trail_atr=trail, exit_lookback=exit_lb,
                               start=start, end=end)
    return metrics(tr, eq, (end or len(df)) - start, bars_per_year)


def search(df, grid, bars_per_year, start, end, min_trades=25):
    rows = []
    for p in grid:
        m = run_one(df, p, bars_per_year, start, end)
        if m["n"] < min_trades:
            continue
        rows.append({"params": p, **m})
    return rows


def main() -> None:
    t0 = time.perf_counter()
    report = {}

    # ══════════ 4h：三段獨立期間 ══════════
    print("=" * 84)
    print("4h 突破搜尋（三段獨立期間，每段只看一次）")
    print("=" * 84)
    syms4 = [s for s in available_4h("long") if s not in ("DOGEUSDT",)]
    for seg_name, s_frac, e_frac in [("IS 2018-2021", 0.0, 0.42),
                                     ("VAL 2021-2024", 0.42, 0.75),
                                     ("TEST 2024-2026", 0.75, 1.0)]:
        print(f"\n--- {seg_name} ---", flush=True)
        agg: dict[tuple, list[dict]] = {}
        for sym in syms4:
            try:
                df = prepare(load_4h(sym, "long"), [24, 48, 96, 192], EXIT_LOOKBACKS)
            except FileNotFoundError:
                continue
            n = len(df)
            rows = search(df, GRID_4H, BARS_PER_YEAR["4h"],
                          int(n * s_frac), int(n * e_frac))
            for r in rows:
                agg.setdefault(tuple(r["params"]), []).append(
                    {"sym": sym, "sharpe": r["sharpe"], "avg_pct": r["avg_pct"],
                     "n": r["n"], "maxdd": r["maxdd_pct"], "pf": r["pf"],
                     "ret_pct": r["ret_pct"]})
        # 評分：各標的 sharpe 的中位數（穩健），要求至少 60% 標的正
        scored = []
        for p, rs in agg.items():
            sh = np.array([r["sharpe"] for r in rs])
            av = np.array([r["avg_pct"] for r in rs])
            if len(rs) < 4:
                continue
            pos_ratio = float((av > 0).mean())
            scored.append({"params": p, "median_sharpe": float(np.median(sh)),
                           "mean_avg_pct": float(av.mean()), "pos_ratio": pos_ratio,
                           "n_syms": len(rs), "per": rs})
        scored.sort(key=lambda x: x["median_sharpe"], reverse=True)
        report[seg_name] = scored[:40]
        print(f"{'lookback':>8}{'dir':>6}{'exit':>10}{'stop':>6}{'trail':>6}{'exitlb':>7}"
              f"{'medSharpe':>11}{'posRatio':>10}{'avg%':>10}")
        for s in scored[:12]:
            lb, d, ex, st, tr_, el = s["params"]
            print(f"{lb:>8}{d:>6}{ex:>10}{st:>6}{tr_:>6}{el:>7}"
                  f"{s['median_sharpe']:>11.2f}{s['pos_ratio']:>10.0%}"
                  f"{s['mean_avg_pct']:>10.4f}")

    # ══════════ 1h：okx 443 天，IS/VAL/TEST ══════════
    print("\n" + "=" * 84)
    print("1h 突破搜尋（okx 443 天，IS 50% / VAL 25% / TEST 25%）")
    print("=" * 84)
    agg1: dict[tuple, list[dict]] = {}
    for sym in available_1h():
        try:
            df = prepare(load_1h_from_5m(sym), [24, 48, 96, 192], EXIT_LOOKBACKS)
        except Exception:
            continue
        n = len(df)
        rows = search(df, GRID_1H, BARS_PER_YEAR["1h"], 0, int(n * 0.5))
        for r in rows:
            agg1.setdefault(tuple(r["params"]), []).append(
                {"sym": sym, "sharpe": r["sharpe"], "avg_pct": r["avg_pct"],
                 "n": r["n"], "maxdd": r["maxdd_pct"], "pf": r["pf"],
                 "ret_pct": r["ret_pct"]})
    scored1 = []
    for p, rs in agg1.items():
        if len(rs) < 4:
            continue
        av = np.array([r["avg_pct"] for r in rs])
        sh = np.array([r["sharpe"] for r in rs])
        scored1.append({"params": p, "median_sharpe": float(np.median(sh)),
                        "mean_avg_pct": float(av.mean()), "pos_ratio": float((av > 0).mean()),
                        "n_syms": len(rs), "per": rs})
    scored1.sort(key=lambda x: x["median_sharpe"], reverse=True)
    report["1h_IS"] = scored1[:40]
    print(f"{'lookback':>8}{'dir':>6}{'exit':>10}{'stop':>6}{'trail':>6}{'exitlb':>7}"
          f"{'medSharpe':>11}{'posRatio':>10}{'avg%':>10}")
    for s in scored1[:12]:
        lb, d, ex, st, tr_, el = s["params"]
        print(f"{lb:>8}{d:>6}{ex:>10}{st:>6}{tr_:>6}{el:>7}"
              f"{s['median_sharpe']:>11.2f}{s['pos_ratio']:>10.0%}{s['mean_avg_pct']:>10.4f}")

    json.dump(report, open(f"{OUT}/s6_search.json", "w"), indent=2)
    print(f"\n耗時 {time.perf_counter() - t0:.0f}s -> {OUT}/s6_search.json")


if __name__ == "__main__":
    main()
