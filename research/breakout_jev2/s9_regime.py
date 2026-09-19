#!/usr/bin/env python3
"""Stage 9：regime 過濾的突破策略（針對 Stage 8 發現的 regime 依賴）。

Stage 8 發現：4h 突破在趨勢年（2019-2021、2024）大幅為正，在盤整/熊年（2022、2025）為負。
這是趨勢跟隨的已知性質 → 問題不是「有沒有 edge」，而是「能不能先判斷現在能不能跑」。

嚴格協定：
  - 過濾器與參數**只在 2018-2023 開發**（不看 2024-2026）
  - 2024-2026 **只測一次**，且只用一個配置
  - 過濾器必須是標準、事先講得通的（不用挑過的魔法閾值）：
      trend : 只在 close > EMA200（多）/ close < EMA200（空）時進場
      vol   : 只在 ATR% 位於其歷史 20-80 百分位時進場（避開死盤與暴走）
      both  : 兩者同時
  - 對照：無過濾
"""
import json
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, "/root/Crypto-Backtesting-Lab")
from research.breakout_jev2.lib_breakout import backtest_breakout, metrics, prepare
from research.breakout_jev2.lib_data_multi import (
    BARS_PER_YEAR, available_1h, load_1h_from_5m, load_4h,
)

OUT = "/root/Crypto-Backtesting-Lab/runtime/breakout_jev2"
EXIT_LOOKBACKS = [12, 24, 48, 96]
LBS = [24, 48, 96, 192]
SYMS4 = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT", "XRPUSDT"]

DEV = ("2018-01-01", "2024-01-01")     # 開發期
HOLD = ("2024-01-01", "2027-01-01")    # 留出期（只測一次）


def add_regime(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ema200"] = out["close"].ewm(span=200, adjust=False).mean()
    out["atr_pct"] = out["atr"] / out["close"]
    out["atr_rank"] = out["atr_pct"].rolling(500, min_periods=200).rank(pct=True)
    return out


def run_filtered(df, p, flt, bars_per_year, s, e):
    """先算 mask，再用同一引擎跑（mask 為 0 的棒不進場）。"""
    lb, d, ex, st, tr_, el = p
    # 以極端通道值「關掉」被過濾的棒
    d2 = df.copy()
    ema = d2["ema200"].values
    rank = d2["atr_rank"].values
    c = d2["close"].values
    block_long = np.zeros(len(d2), dtype=bool)
    block_short = np.zeros(len(d2), dtype=bool)
    if flt in ("trend", "both"):
        block_long |= ~(c > ema)
        block_short |= ~(c < ema)
    if flt in ("vol", "both"):
        ok = ~np.isnan(rank) & (rank >= 0.20) & (rank <= 0.80)
        block_long |= ~ok
        block_short |= ~ok
    d2.loc[block_long, f"don_hi_{lb}"] = 1e12
    d2.loc[block_short, f"don_lo_{lb}"] = -1e12

    tr, eq = backtest_breakout(d2, lookback=lb, direction=d, exit_method=ex,
                               stop_atr=st, target_atr=tr_, trail_atr=tr_,
                               exit_lookback=el, start=s, end=e)
    return tr, eq, metrics(tr, eq, e - s, bars_per_year)


def main() -> None:
    report = {}

    # ─────── 4h ───────
    print("=" * 90)
    print("4h：regime 過濾（開發 2018-2023，留出 2024-2026 只測一次）")
    print("=" * 90)
    F = {}
    for s in SYMS4:
        try:
            F[s] = add_regime(prepare(load_4h(s, "long"), LBS, EXIT_LOOKBACKS))
        except FileNotFoundError:
            pass

    def eval_seg(flt, p, seg):
        per = []
        for sym, df in F.items():
            ts = df["timestamp"]
            m = (ts >= seg[0]) & (ts < seg[1])
            idx = np.where(m.values)[0]
            if len(idx) < 150:
                continue
            tr, eq, mm = run_filtered(df, p, flt, BARS_PER_YEAR["4h"],
                                      int(idx[0]), int(idx[-1]) + 1)
            if mm["n"] < 3:
                continue
            per.append({"sym": sym, **{k: mm[k] for k in ("sharpe", "avg_pct", "n", "maxdd_pct", "pf", "ret_pct")}})
        return per

    def summ(per):
        if len(per) < 4:
            return None
        sh = np.array([x["sharpe"] for x in per])
        av = np.array([x["avg_pct"] for x in per])
        return {"median_sharpe": float(np.median(sh)), "mean_avg_pct": float(av.mean()),
                "pos_ratio": float((av > 0).mean()), "n_syms": len(per),
                "total_n": int(sum(x["n"] for x in per)), "per": per}

    GRID = [(lb, d, ex, st, 3.0, el) for lb in LBS for d in ("long", "both")
            for ex in ("donchian", "trail") for st in (2.5, 4.0) for el in (48, 96)]
    dev_results = {}
    for flt in ("none", "trend", "vol", "both"):
        for p in GRID:
            per = eval_seg(flt, p, DEV)
            s_ = summ(per)
            if s_:
                dev_results[(flt, tuple(p))] = s_

    # 開發期選最穩者：中位 Sharpe 高 + 正標準高 + 交易數足
    cands = [(k, v) for k, v in dev_results.items()
             if v["median_sharpe"] > 0.3 and v["pos_ratio"] >= 0.7 and v["total_n"] >= 100]
    cands.sort(key=lambda kv: kv[1]["median_sharpe"], reverse=True)
    print(f"\n開發期(2018-2023)合格候選（中位Sharpe>0.3 且 ≥70%標的正 且 ≥100筆）：{len(cands)}")
    print(f"{'filter':>8}{'params':>40}{'medSh':>9}{'pos':>7}{'avg%':>10}{'n':>7}")
    for (flt, p), v in cands[:10]:
        print(f"{flt:>8}{str(p):>40}{v['median_sharpe']:>9.2f}{v['pos_ratio']:>7.0%}"
              f"{v['mean_avg_pct']:>10.4f}{v['total_n']:>7}")

    if cands:
        (flt, p), dev = cands[0]
        print(f"\n選定（依開發期，留出期未看）: filter={flt}  params={p}")
        per_h = eval_seg(flt, p, HOLD)
        h = summ(per_h)
        print(f"\n=== 4h 留出期 2024-2026（只跑一次）===")
        print(f"  開發 2018-2023: 中位 Sharpe {dev['median_sharpe']:+.2f}  "
              f"正標的 {dev['pos_ratio']:.0%}  平均 {dev['mean_avg_pct']:+.4f}%/筆  n={dev['total_n']}")
        if h:
            print(f"  留出 2024-2026: 中位 Sharpe {h['median_sharpe']:+.2f}  "
                  f"正標的 {h['pos_ratio']:.0%}  平均 {h['mean_avg_pct']:+.4f}%/筆  n={h['total_n']}")
            for r in sorted(h["per"], key=lambda x: -x["sharpe"]):
                print(f"    {r['sym']:10s} Sharpe {r['sharpe']:+6.2f}  平均 {r['avg_pct']:+.4f}%  "
                      f"n={r['n']:>4}  MaxDD {r['maxdd_pct']:+7.1f}%  PF {r['pf']:5.2f}  "
                      f"總報酬 {r['ret_pct']:+.1f}%")
        report["4h"] = {"filter": flt, "params": list(p), "dev": dev, "holdout": h}

    # ─────── 1h ───────
    print("\n" + "=" * 90)
    print("1h：regime 過濾（開發前 75%，留出最後 25% 只測一次）")
    print("=" * 90)
    F1 = {s: add_regime(prepare(load_1h_from_5m(s), LBS, EXIT_LOOKBACKS))
          for s in available_1h()}

    def eval_1h(flt, p, seg_name):
        per = []
        for sym, df in F1.items():
            n = len(df)
            a, b = (0.0, 0.75) if seg_name == "dev" else (0.75, 1.0)
            s, e = int(n * a), int(n * b)
            if e - s < 200:
                continue
            tr, eq, mm = run_filtered(df, p, flt, BARS_PER_YEAR["1h"], s, e)
            if mm["n"] < 5:
                continue
            per.append({"sym": sym, **{k: mm[k] for k in ("sharpe", "avg_pct", "n", "maxdd_pct", "pf", "ret_pct")}})
        return per

    dev1 = {}
    for flt in ("none", "trend", "vol", "both"):
        for p in GRID:
            s_ = summ(eval_1h(flt, p, "dev"))
            if s_:
                dev1[(flt, tuple(p))] = s_
    c1 = [(k, v) for k, v in dev1.items()
          if v["median_sharpe"] > 0.3 and v["pos_ratio"] >= 0.7 and v["total_n"] >= 60]
    c1.sort(key=lambda kv: kv[1]["median_sharpe"], reverse=True)
    print(f"\n開發期合格候選：{len(c1)}")
    print(f"{'filter':>8}{'params':>40}{'medSh':>9}{'pos':>7}{'avg%':>10}{'n':>7}")
    for (flt, p), v in c1[:10]:
        print(f"{flt:>8}{str(p):>40}{v['median_sharpe']:>9.2f}{v['pos_ratio']:>7.0%}"
              f"{v['mean_avg_pct']:>10.4f}{v['total_n']:>7}")
    if c1:
        (flt, p), dev = c1[0]
        print(f"\n選定（依開發期）: filter={flt}  params={p}")
        h1 = summ(eval_1h(flt, p, "holdout"))
        print(f"\n=== 1h 留出期最後 25%（只跑一次）===")
        print(f"  開發 前75%: 中位 Sharpe {dev['median_sharpe']:+.2f}  正標的 {dev['pos_ratio']:.0%}  "
              f"平均 {dev['mean_avg_pct']:+.4f}%/筆")
        if h1:
            print(f"  留出 後25%: 中位 Sharpe {h1['median_sharpe']:+.2f}  正標的 {h1['pos_ratio']:.0%}  "
                  f"平均 {h1['mean_avg_pct']:+.4f}%/筆  n={h1['total_n']}")
            for r in sorted(h1["per"], key=lambda x: -x["sharpe"]):
                print(f"    {r['sym']:6s} Sharpe {r['sharpe']:+6.2f}  平均 {r['avg_pct']:+.4f}%  "
                      f"n={r['n']:>4}  PF {r['pf']:5.2f}  總報酬 {r['ret_pct']:+.1f}%")
        report["1h"] = {"filter": flt, "params": list(p), "dev": dev, "holdout": h1}

    json.dump(report, open(f"{OUT}/s9_regime.json", "w"), indent=2)
    print(f"\n-> {OUT}/s9_regime.json")


if __name__ == "__main__":
    main()
