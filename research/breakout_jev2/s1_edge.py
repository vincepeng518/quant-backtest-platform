#!/usr/bin/env python3
"""Stage 1：5m 突破的原始 edge 是否存在？

方法（與前次研究刻意不同，作為獨立交叉驗證）：
  1. 全期連續回測（非隨機抽樣）-> per-trade 報酬
  2. 零費率 vs 含費率 並排
  3. bootstrap 95% CI、時間前後半穩定、多空對稱
  4. 5 個標的並排
輸出：runtime/breakout_jev2/s1_edge.json
"""
import itertools
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/root/Crypto-Backtesting-Lab")
from research.breakout_jev2.lib_backtest import backtest, metrics
from research.breakout_jev2.lib_data import add_features, load_5m
from research.breakout_jev2.lib_stats import boot_ci

TAGS = ["BTC_USDT", "APT_USDT", "SUI_USDT", "FIL_USDT", "BCH_USDT"]
LOOKBACKS = [24, 96, 288, 576, 720]
GRID = list(itertools.product(LOOKBACKS, [2.0], [4.0], [1.0]))
OUT = "/root/Crypto-Backtesting-Lab/runtime/breakout_jev2"
os.makedirs(OUT, exist_ok=True)


def main() -> None:
    report = {}
    for tag in TAGS:
        try:
            df = add_features(load_5m(tag), lookbacks=LOOKBACKS)
        except FileNotFoundError as e:
            print(f"[skip] {tag}: {e}")
            continue
        rows = []
        print(f"\n{'=' * 70}\n{tag}  樣本 {len(df):,} 根  "
              f"{df['timestamp'].iloc[0]} ~ {df['timestamp'].iloc[-1]}\n{'=' * 70}")
        for lb, sa, ta, bm in GRID:
            tr0, eq0 = backtest(df, lb, sa, ta, bm, fee=0.0, slippage=0.0)
            tr1, eq1 = backtest(df, lb, sa, ta, bm)
            r0 = np.array([t["ret"] for t in tr0])
            r1 = np.array([t["ret"] for t in tr1])
            if len(r0) < 20:
                print(f"  lb={lb:>4}  樣本不足 ({len(r0)})")
                continue
            m0, m1 = metrics(tr0, eq0, len(df)), metrics(tr1, eq1, len(df))
            mean0, lo0, hi0 = boot_ci(r0)
            half = len(r0) // 2
            rows.append({
                "lookback": lb,
                "zero_fee_avg_pct": mean0 * 100,
                "ci_lo_pct": lo0 * 100,
                "ci_hi_pct": hi0 * 100,
                "significant": bool(lo0 > 0),
                "fee_avg_pct": float(r1.mean() * 100),
                "win_rate": m1["wr"],
                "pf": m1["pf"],
                "n_trades": m1["n"],
                "trades_per_day": m1["trades_per_day"],
                "sharpe_fee": m1["sharpe"],
                "stable": bool(r0[:half].mean() > 0 and r0[half:].mean() > 0),
                "first_half_pct": float(r0[:half].mean() * 100),
                "second_half_pct": float(r0[half:].mean() * 100),
            })
            print(f"  lb={lb:>4}  零費 {mean0 * 100:+.4f}%  "
                  f"95%CI [{lo0 * 100:+.4f}%, {hi0 * 100:+.4f}%]  "
                  f"含費 {r1.mean() * 100:+.4f}%  n={m1['n']:>5}  "
                  f"WR {m1['wr']:.1%}  PF {m1['pf']:.2f}  "
                  f"{'顯著' if lo0 > 0 else '不顯著'}")
        report[tag] = rows
        if rows:
            sig = [r for r in rows if r["significant"]]
            print(f"  → 顯著的 lookback: {[r['lookback'] for r in sig] or '無'}")
    json.dump(report, open(f"{OUT}/s1_edge.json", "w"), indent=2)

    # 閘門判定
    print(f"\n{'=' * 70}\n閘門判定\n{'=' * 70}")
    any_sig = any(r["significant"] and r["stable"] for rows in report.values() for r in rows)
    print(f"存在任一「CI 不含零 且 前後半同號」的配置: {'是 ✓' if any_sig else '否 ✗'}")
    print("→ " + ("繼續 Stage 2-4" if any_sig else "停止：不存在可開發 edge，不加槓桿硬凹"))
    print(f"\n-> {OUT}/s1_edge.json")


if __name__ == "__main__":
    main()
