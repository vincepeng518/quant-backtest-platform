#!/usr/bin/env python3
"""Stage 10：橫斷面大樣本檢定（用 okx_data 的數百個 4h 標的）。

為什麼要做：Stage 6-9 只用 7 個標的，中位數統計噪音大，無法區分「沒 edge」與「樣本不夠」。
okx_data 有 431 個 4h 標的（多數 2000-10000 根）→ 可以做真正的橫斷面檢定：
  若真有 edge，應該在一兩百個標的的多數上都看得到，而不是靠少數幾檔。

協定：
  - 對每個標的：**時間前 60% 當開發，後 40% 當留出**（每檔獨立的時間分割）
  - 用**固定**參數（不在每檔上優化 → 無 per-symbol 過擬合）
  - 分別報告開發期與留出期的橫斷面分布
  - 若開發期正、留出期也正且比率高 → 真 edge；若留出期崩塌 → 之前是過擬合
"""
import glob
import json
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, "/root/Crypto-Backtesting-Lab")
from research.breakout_jev2.lib_breakout import backtest_breakout, metrics, prepare
from research.breakout_jev2.lib_data_multi import BARS_PER_YEAR

OUT = "/root/Crypto-Backtesting-Lab/runtime/breakout_jev2"
EXIT_LOOKBACKS = [12, 24, 48, 96]
LBS = [24, 48, 96, 192]
MIN_BARS = 2500

CONFIGS = {
    "donchian_both_lb96":  (96, "both", "donchian", 4.0, 3.0, 48),
    "donchian_long_lb96":  (96, "long", "donchian", 4.0, 3.0, 48),
    "donchian_both_lb48":  (48, "both", "donchian", 4.0, 3.0, 96),
    "trail_both_lb192":    (192, "both", "trail", 2.5, 3.0, 48),
    "oco_both_lb96":       (96, "both", "oco", 2.0, 4.0, 48),   # 對照：舊做法
}


def load_okx_4h(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df[["timestamp", "open", "high", "low", "close", "volume"]] \
             .dropna().sort_values("timestamp").reset_index(drop=True)


def main() -> None:
    files = sorted(glob.glob("/root/okx_data/*_4h.csv"))
    print(f"okx_data 4h 檔數 {len(files)}，篩選 >= {MIN_BARS} 根…")
    frames = {}
    for p in files:
        sym = os.path.basename(p)[:-7]
        try:
            df = load_okx_4h(p)
        except Exception:
            continue
        if len(df) < MIN_BARS:
            continue
        frames[sym] = prepare(df, LBS, EXIT_LOOKBACKS)
    print(f"合格標的 {len(frames)} 檔")
    starts = [f["timestamp"].iloc[0] for f in frames.values()]
    ends = [f["timestamp"].iloc[-1] for f in frames.values()]
    print(f"  期間涵蓋 {min(starts).date()} ~ {max(ends).date()}")
    lens = np.array([len(f) for f in frames.values()])
    print(f"  根數中位 {int(np.median(lens))}  min {lens.min()}  max {lens.max()}")

    report = {}
    for name, cfg in CONFIGS.items():
        lb, d, ex, st, tr_, el = cfg
        dev, hold = [], []
        for sym, df in frames.items():
            n = len(df)
            cut = int(n * 0.6)
            if cut < 400 or n - cut < 300:
                continue
            for label, (s, e), bag in [("dev", (0, cut), dev), ("hold", (cut, n), hold)]:
                tr, eq = backtest_breakout(df, lookback=lb, direction=d, exit_method=ex,
                                           stop_atr=st, target_atr=tr_, trail_atr=tr_,
                                           exit_lookback=el, start=s, end=e)
                m = metrics(tr, eq, e - s, BARS_PER_YEAR["4h"])
                if m["n"] >= 1:
                    bag.append({"sym": sym, "avg_pct": m["avg_pct"], "sharpe": m["sharpe"],
                                "n": m["n"], "maxdd_pct": m["maxdd_pct"], "ret_pct": m["ret_pct"]})
        if not dev or not hold:
            continue
        dv = np.array([x["avg_pct"] for x in dev])
        hd = np.array([x["avg_pct"] for x in hold])
        dsh = np.array([x["sharpe"] for x in dev])
        hsh = np.array([x["sharpe"] for x in hold])
        report[name] = {
            "params": list(cfg),
            "dev": {"n_syms": len(dv), "mean_pct": float(dv.mean()), "median_pct": float(np.median(dv)),
                    "pos_ratio": float((dv > 0).mean()), "median_sharpe": float(np.median(dsh)),
                    "mean_trades": float(np.mean([x["n"] for x in dev]))},
            "hold": {"n_syms": len(hd), "mean_pct": float(hd.mean()), "median_pct": float(np.median(hd)),
                     "pos_ratio": float((hd > 0).mean()), "median_sharpe": float(np.median(hsh)),
                     "mean_trades": float(np.mean([x["n"] for x in hold]))},
        }
        r = report[name]
        print(f"\n{name}  params={cfg}")
        print(f"  DEV  (前60%): {r['dev']['n_syms']} 檔  平均 {r['dev']['mean_pct']:+.4f}%  "
              f"中位 {r['dev']['median_pct']:+.4f}%  正標的 {r['dev']['pos_ratio']:.0%}  "
              f"中位Sh {r['dev']['median_sharpe']:+.2f}")
        print(f"  HOLD (後40%): {r['hold']['n_syms']} 檔  平均 {r['hold']['mean_pct']:+.4f}%  "
              f"中位 {r['hold']['median_pct']:+.4f}%  正標的 {r['hold']['pos_ratio']:.0%}  "
              f"中位Sh {r['hold']['median_sharpe']:+.2f}")

        # 跨符號 bootstrap：留出期平均報酬是否顯著 > 0
        if len(hd) >= 20:
            rng = np.random.default_rng(7)
            boot = np.array([rng.choice(hd, len(hd), replace=True).mean() for _ in range(5000)])
            p = float((boot <= 0).mean())
            r["hold"]["boot_p_mean_le_0"] = p
            print(f"  HOLD 橫斷面 bootstrap: 平均 {hd.mean():+.4f}%  "
                  f"95%CI [{np.percentile(boot, 2.5):+.4f}, {np.percentile(boot, 97.5):+.4f}]  "
                  f"p(mean<=0)={p:.3f}  {'顯著 ✓' if p < 0.05 else '不顯著 ✗'}")

    json.dump(report, open(f"{OUT}/s10_cross_section.json", "w"), indent=2)

    print("\n" + "=" * 90)
    print("彙總：哪些配置在留出期橫斷面顯著為正？")
    print("=" * 90)
    winners = [(k, v) for k, v in report.items()
               if v["hold"].get("boot_p_mean_le_0", 1) < 0.05 and v["hold"]["mean_pct"] > 0]
    if winners:
        for k, v in winners:
            print(f"  {k:22s} 留出平均 {v['hold']['mean_pct']:+.4f}%  "
                  f"正標的 {v['hold']['pos_ratio']:.0%}  p={v['hold']['boot_p_mean_le_0']:.4f}")
    else:
        print("  （無）→ 沒有任何配置在數百個標的的留出期橫斷面顯著為正")
    print(f"\n-> {OUT}/s10_cross_section.json")


if __name__ == "__main__":
    main()
