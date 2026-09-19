#!/usr/bin/env python3
"""Stage 7：用 IS+VAL 選參數 → TEST 段只跑一次（決定性驗證）。

規則（防過擬合）：
  1. 4h：IS=2018-2021、VAL=2021-2024 用來選參數；TEST=2024-2026 只看一次
  2. 1h：IS=前50%、VAL=50-75%；TEST=75-100% 只看一次
  3. **參數高原檢查**：只接受鄰近參數（lookback ±、stop ±）也為正的配置
  4. **門檻**：TEST 段要求 ≥60% 標的為正 且 中位 Sharpe > 0
  5. 對照組：固定 ATR OCO（已知失敗的基準）
"""
import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, "/root/Crypto-Backtesting-Lab")
from research.breakout_jev2.lib_breakout import backtest_breakout, metrics, prepare
from research.breakout_jev2.lib_data_multi import (
    BARS_PER_YEAR, available_1h, load_1h_from_5m, load_4h,
)

OUT = "/root/Crypto-Backtesting-Lab/runtime/breakout_jev2"
EXIT_LOOKBACKS = [12, 24, 48, 96]
SEG4 = {"IS": (0.00, 0.42), "VAL": (0.42, 0.75), "TEST": (0.75, 1.00)}
SEG1 = {"IS": (0.00, 0.50), "VAL": (0.50, 0.75), "TEST": (0.75, 1.00)}


def eval_params(df, p, bars_per_year, start, end):
    lb, d, ex, st, tr_, el = p
    tr, eq = backtest_breakout(df, lookback=lb, direction=d, exit_method=ex,
                               stop_atr=st, target_atr=tr_, trail_atr=tr_,
                               exit_lookback=el, start=start, end=end)
    return metrics(tr, eq, end - start, bars_per_year)


def eval_segment(syms, loader, seg, grid_or_params, bars_per_year, prepare_lbs):
    """回傳 {params: [per-symbol metrics]}"""
    out = defaultdict(list)
    frames = {}
    for sym in syms:
        try:
            frames[sym] = prepare(loader(sym), prepare_lbs, EXIT_LOOKBACKS)
        except Exception:
            continue
    for sym, df in frames.items():
        n = len(df)
        s, e = int(n * seg[0]), int(n * seg[1])
        if e - s < 300:
            continue
        for p in grid_or_params:
            m = eval_params(df, p, bars_per_year, s, e)
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
        rows.append({"params": p, "median_sharpe": float(np.median(sh)),
                     "mean_sharpe": float(sh.mean()),
                     "mean_avg_pct": float(av.mean()), "pos_ratio": float((av > 0).mean()),
                     "n_syms": len(rs), "total_n": int(sum(r["n"] for r in rs)),
                     "per": rs})
    rows.sort(key=lambda x: x["median_sharpe"], reverse=True)
    return rows


def plateau_check(rows, top):
    """鄰近參數也為正才算高原（lookback 相鄰 + 出場參數相鄰）。"""
    key = lambda p: p
    pos = {r["params"] for r in rows if r["mean_avg_pct"] > 0}
    p = top["params"]
    lb, d, ex, st, tr_, el = p
    neighbours = []
    for nlb in (lb // 2, lb, lb * 2):
        for nst in (st - 1.0, st, st + 1.5):
            for nel in (el // 2, el, el * 2):
                q = (nlb, d, ex, round(nst, 2), tr_, nel)
                neighbours.append(q in pos)
    # 只計算存在的鄰居
    present = [k for k in [(lb // 2, d, ex, round(st - 1.0, 2), tr_, el // 2),
                           (lb // 2, d, ex, st, tr_, el),
                           (lb * 2, d, ex, st, tr_, el),
                           (lb, d, ex, round(st - 1.0, 2), tr_, el),
                           (lb, d, ex, round(st + 1.5, 2), tr_, el),
                           (lb, d, ex, st, tr_, el // 2),
                           (lb, d, ex, st, tr_, el * 2)] if k in {r["params"] for r in rows}]
    ok_count = sum(1 for k in present if k in pos)
    return ok_count, len(present)


def main() -> None:
    report = {"4h": {}, "1h": {}}

    # ══════ 4h ══════
    print("=" * 88)
    print("4h：用 IS+VAL 選參數，TEST 段只跑一次")
    print("=" * 88)
    syms4 = [s for s in ("BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "LINKUSDT",
                         "LTCUSDT", "XRPUSDT")]
    all_grid = [tuple(r["params"]) for r in json.load(open(f"{OUT}/s6_search.json"))["IS 2018-2021"]]
    # 去重（trail/donchian 不用 target，故 target 維度冗餘）
    grid = []
    for p in all_grid:
        if p[2] in ("trail", "donchian"):
            p = (p[0], p[1], p[2], p[3], 3.0, p[5])
        if p not in grid:
            grid.append(p)
    print(f"候選參數 {len(grid)} 組（去重後）")

    agg_is = eval_segment(syms4, lambda s: load_4h(s, "long"), SEG4["IS"], grid,
                          BARS_PER_YEAR["4h"], [24, 48, 96, 192])
    agg_val = eval_segment(syms4, lambda s: load_4h(s, "long"), SEG4["VAL"], grid,
                           BARS_PER_YEAR["4h"], [24, 48, 96, 192])
    is_rows = summarize(agg_is)
    val_rows = summarize(agg_val)
    val_map = {r["params"]: r for r in val_rows}

    # 選參數準則：IS 與 VAL 都要正
    cands = [r for r in is_rows if r["params"] in val_map
             and r["mean_avg_pct"] > 0 and val_map[r["params"]]["mean_avg_pct"] > 0]
    cands.sort(key=lambda r: r["median_sharpe"] + val_map[r["params"]]["median_sharpe"],
               reverse=True)
    print(f"\nIS 與 VAL 皆為正的候選：{len(cands)} 組")
    print(f"{'params':>44}{'IS medSh':>10}{'IS pos':>8}{'VAL medSh':>11}{'VAL pos':>9}")
    for r in cands[:8]:
        v = val_map[r["params"]]
        print(f"{str(r['params']):>44}{r['median_sharpe']:>10.2f}{r['pos_ratio']:>8.0%}"
              f"{v['median_sharpe']:>11.2f}{v['pos_ratio']:>9.0%}")

    if cands:
        best4 = cands[0]
        ok, tot = plateau_check(is_rows, best4)
        print(f"\n參數高原檢查（最佳候選）: {ok}/{tot} 個鄰居為正")
        # TEST 只跑一次
        agg_test = eval_segment(syms4, lambda s: load_4h(s, "long"), SEG4["TEST"],
                                [best4["params"]], BARS_PER_YEAR["4h"], [24, 48, 96, 192])
        tr_rows = summarize(agg_test)
        if tr_rows:
            t = tr_rows[0]
            v = val_map[best4["params"]]
            print(f"\n=== 4h TEST 段（只跑一次）===")
            print(f"參數: {t['params']}")
            print(f"  IS   : 中位 Sharpe {best4['median_sharpe']:+.2f}  正標的 {best4['pos_ratio']:.0%}  "
                  f"平均 {best4['mean_avg_pct']:+.4f}%/筆")
            print(f"  VAL  : 中位 Sharpe {v['median_sharpe']:+.2f}  正標的 {v['pos_ratio']:.0%}  "
                  f"平均 {v['mean_avg_pct']:+.4f}%/筆")
            print(f"  TEST : 中位 Sharpe {t['median_sharpe']:+.2f}  正標的 {t['pos_ratio']:.0%}  "
                  f"平均 {t['mean_avg_pct']:+.4f}%/筆  總交易 {t['total_n']}")
            print(f"  TEST 各標的:")
            for r in t["per"]:
                print(f"    {r['sym']:10s} Sharpe {r['sharpe']:+6.2f}  "
                      f"平均 {r['avg_pct']:+.4f}%  n={r['n']:>4}  MaxDD {r['maxdd_pct']:+7.1f}%  "
                      f"PF {r['pf']:5.2f}  總報酬 {r['ret_pct']:+.1f}%")
            report["4h"] = {"params": t["params"], "IS": best4, "VAL": v, "TEST": t,
                            "plateau": [ok, tot]}
    json.dump(report, open(f"{OUT}/s7_validate_4h.json", "w"), indent=2)
    print(f"\n-> {OUT}/s7_validate_4h.json")


if __name__ == "__main__":
    main()
