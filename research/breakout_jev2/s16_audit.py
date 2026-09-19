#!/usr/bin/env python3
"""Stage 16：追查 Stage 15 留出期「+0.30 Sharpe / 71% 標的正」與 Stage 7「+0.06」的差異。

Stage 15 用「共同時間軸」（16,506 根），Stage 7 用「各檔全長」（18,777 根）。
本階段把兩者放在同一基礎上重跑，找出差異來源。可能的原因：
  a) 時間軸不同 → 留出期切點不同（Stage 15 前60% = 2024-06；Stage 7 前75% = 2024-10）
  b) Stage 15 的 reindex 引入錯位或 look-ahead
  c) 樣本數不同造成的隨機差異
  d) Stage 15 有實質 bug（例如 mask 與 df 對齊錯誤）

做法：用**完全相同**的函式與資料切法重跑，逐項對照。
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


def run(df, s, e):
    t, eq = backtest_breakout(df, lookback=lb, direction=d, exit_method=ex,
                              stop_atr=st, target_atr=tr_, trail_atr=tr_,
                              exit_lookback=el, start=s, end=e)
    return t, metrics(t, eq, e - s, BARS_PER_YEAR["4h"])


def main() -> None:
    print("=" * 94)
    print("追查：Stage 15 留出 +0.30 vs Stage 7 TEST +0.06 的差異來源")
    print("=" * 94)

    frames_full, frames_common = {}, {}
    for sym in SYMS4:
        try:
            frames_full[sym] = prepare(load_4h(sym, "long"), LBS, EXIT_LOOKBACKS)
        except FileNotFoundError:
            continue
    common = None
    for df in frames_full.values():
        s = set(df["timestamp"])
        common = s if common is None else (common & s)
    common_idx = sorted(common)
    print(f"各檔全長: {sorted(len(v) for v in frames_full.values())} 根")
    print(f"共同時間軸: {len(common_idx):,} 根")
    print(f"  共同軸起訖: {common_idx[0]} ~ {common_idx[-1]}")

    # 三種切法並排
    SCHEMES = [
        ("A. 各檔全長, 前75%", "full", 0.75),
        ("B. 共同軸, 前75%", "common", 0.75),
        ("C. 共同軸, 前60% (Stage15)", "common", 0.60),
    ]
    for label, mode, frac in SCHEMES:
        print(f"\n--- {label} ---")
        rows = []
        for sym, df in frames_full.items():
            if mode == "common":
                d2 = df.set_index("timestamp").reindex(common_idx).reset_index()
                d2 = d2.rename(columns={"index": "timestamp"}).dropna(
                    subset=["open", "close"]).reset_index(drop=True)
            else:
                d2 = df
            n = len(d2)
            cut = int(n * frac)
            t, m = run(d2, cut, n)
            if m["n"] < 3:
                continue
            rows.append({"sym": sym, **{k: m[k] for k in ("sharpe", "avg_pct", "n", "ret_pct")},
                         "cut_date": str(pd.Timestamp(d2["timestamp"].iloc[cut]))[:10],
                         "n_bars": n})
        if not rows:
            print("  無交易")
            continue
        sh = np.array([r["sharpe"] for r in rows])
        av = np.array([r["avg_pct"] for r in rows])
        print(f"  中位Sharpe {np.median(sh):+.2f}  平均報酬 {av.mean():+.4f}%  "
              f"正標的 {np.mean(av > 0):.0%}  總交易 {sum(r['n'] for r in rows)}")
        print(f"  留出起點: {rows[0]['cut_date']}  根數: {rows[0]['n_bars']:,}")
        for r in sorted(rows, key=lambda x: -x["sharpe"]):
            print(f"    {r['sym']:>10} Sharpe {r['sharpe']:+6.2f}  平均 {r['avg_pct']:+8.4f}%  "
                  f"n={r['n']:>3}  總報酬 {r['ret_pct']:+8.1f}%")

    # ── 直接檢驗 Stage 15 的 mask 對齊是否正確 ──
    print("\n" + "=" * 94)
    print("檢驗 Stage 15 的 mask 對齊：把 mask 全設為 True，結果應與『無濾網』完全相同")
    print("=" * 94)
    for sym, df in list(frames_full.items())[:2]:
        d2 = df.set_index("timestamp").reindex(common_idx).reset_index()
        d2 = d2.rename(columns={"index": "timestamp"}).dropna(
            subset=["open", "close"]).reset_index(drop=True)
        n = len(d2)
        cut = int(n * 0.6)
        t0, m0 = run(d2, cut, n)
        d3 = d2.copy()
        mask = np.zeros(len(d3), dtype=bool)     # 全部允許
        d3.loc[mask, f"don_hi_{lb}"] = 1e12      # 不生效
        d3.loc[mask, f"don_lo_{lb}"] = -1e12
        t1, m1 = run(d3, cut, n)
        print(f"  {sym:>10} 無mask n={m0['n']} 平均 {m0['avg_pct']:+.4f}%  |  "
              f"空mask n={m1['n']} 平均 {m1['avg_pct']:+.4f}%  "
              f"{'✓ 一致' if m0['n'] == m1['n'] else '✗ 不一致（mask 有問題）'}")

    json.dump({"note": "對照三種切法"}, open(f"{OUT}/s16_audit.json", "w"), indent=2)
    print(f"\n-> {OUT}/s16_audit.json")


if __name__ == "__main__":
    main()
