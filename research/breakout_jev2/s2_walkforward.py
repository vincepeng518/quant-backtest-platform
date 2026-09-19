#!/usr/bin/env python3
"""Stage 2：錨定式（anchored）Walk-Forward + 隨機參數對照。

關鍵設計：
  - IS 永遠從 index 0 起（錨定），每折 OOS 遞增，OOS 彼此不重疊 -> 無重疊污染
  - 每折同時跑 R 組**隨機參數**作為 control
    -> 若「最佳參數的 OOS」贏不過「隨機參數的 OOS P90」，就是過擬合而非 edge
"""
import itertools
import json
import os
import sys

import numpy as np

sys.path.insert(0, "/root/Crypto-Backtesting-Lab")
from research.breakout_jev2.lib_backtest import backtest, metrics
from research.breakout_jev2.lib_data import LOOKBACKS, add_features, load_5m

TAGS = ["BTC_USDT", "APT_USDT", "SUI_USDT", "FIL_USDT", "BCH_USDT"]
GRID = list(itertools.product(LOOKBACKS, [1.0, 2.0, 3.0], [2.0, 4.0, 6.0], [0.28, 1.0]))
OUT = "/root/Crypto-Backtesting-Lab/runtime/breakout_jev2"
N_FOLDS = 5
OOS_BARS = 20_000          # 每折 OOS 約 69 天
RANDOM_CONTROL = 20


def optimize_is(df, is_end: int, grid):
    best = None
    for row in grid:
        tr, eq = backtest(df, *row, end=is_end)
        m = metrics(tr, eq, is_end)
        if m["n"] < 20:
            continue
        if best is None or m["sharpe"] > best[0]["sharpe"]:
            best = (m, row)
    return best


def main() -> None:
    rng = np.random.default_rng(2026)
    out = {}
    for tag in TAGS:
        try:
            df = add_features(load_5m(tag), lookbacks=LOOKBACKS)
        except FileNotFoundError:
            continue
        n = len(df)
        print(f"\n{'=' * 70}\n{tag}  {n:,} 根\n{'=' * 70}", flush=True)
        folds = []
        for k in range(N_FOLDS):
            is_end = int(n * 0.5) + k * OOS_BARS
            oos_end = min(is_end + OOS_BARS, n)
            if oos_end - is_end < 2000 or is_end >= n:
                continue
            opt = optimize_is(df, is_end, GRID)
            if opt is None:
                continue
            m_is, params = opt
            tr_o, eq_o = backtest(df, *params, start=is_end, end=oos_end)
            m_o = metrics(tr_o, eq_o, oos_end - is_end)
            ctrl = []
            for _ in range(RANDOM_CONTROL):
                row = tuple(rng.choice(v) for v in zip(*GRID))
                tr_c, eq_c = backtest(df, *row, start=is_end, end=oos_end)
                ctrl.append(metrics(tr_c, eq_c, oos_end - is_end)["sharpe"])
            ctrl = np.array(ctrl, dtype=float)
            folds.append({
                "fold": k + 1, "is_end": is_end, "oos_end": oos_end,
                "params": list(params),
                "is_sharpe": m_is["sharpe"], "oos_sharpe": m_o["sharpe"],
                "oos_n": m_o["n"], "oos_ret_pct": m_o["ret_pct"],
                "ctrl_median_sharpe": float(np.median(ctrl)),
                "ctrl_p90_sharpe": float(np.percentile(ctrl, 90)),
                "beats_control": bool(m_o["sharpe"] > np.percentile(ctrl, 90)),
            })
            f = folds[-1]
            print(f"  fold {k + 1}: IS Sharpe {f['is_sharpe']:+.3f} -> OOS {f['oos_sharpe']:+.3f} "
                  f"(n={f['oos_n']}, {f['oos_ret_pct']:+.1f}%)  "
                  f"control 中位 {f['ctrl_median_sharpe']:+.3f} / P90 {f['ctrl_p90_sharpe']:+.3f}  "
                  f"{'勝 ✓' if f['beats_control'] else '敗 ✗'}", flush=True)
        oos = [f["oos_sharpe"] for f in folds]
        if oos:
            print(f"  → OOS 平均 {np.mean(oos):+.3f}  正折數 "
                  f"{sum(1 for s in oos if s > 0)}/{len(oos)}  "
                  f"勝過 control 折數 {sum(1 for f in folds if f['beats_control'])}/{len(folds)}")
        out[tag] = folds
    json.dump(out, open(f"{OUT}/s2_walkforward.json", "w"), indent=2)
    print(f"\n-> {OUT}/s2_walkforward.json")


if __name__ == "__main__":
    main()
