#!/usr/bin/env python3
"""Stage 5c：從 jev5_judgements.csv 計算「Jev 判斷 vs 實際報酬」的統計檢定。

回答使用者指定的核心問題：**低 setup 分的單是不是明顯比較虧？**
以及對照組檢定：Jev 選的單 vs 隨機選的單，差異是否顯著。
"""
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/root/Crypto-Backtesting-Lab")
from research.breakout_jev2.lib_data import LOOKBACKS, add_features, load_5m
from research.breakout_jev2.s5a_baseline_rules import add_rule_features

OUT = "/root/Crypto-Backtesting-Lab/runtime/breakout_jev2"
LOOKBACK, BRK_MAX = 288, 1.0
STOP_ATR, TARGET_ATR, MAX_HOLD = 2.0, 4.0, 288
FEE, SLIP = 0.0005, 0.0002


def trade_return(df: pd.DataFrame, i: int) -> float | None:
    """該訊號棒的實際單筆淨報酬（與 run_mask 同一套規則）。"""
    n = len(df)
    o, h, l, c = (df[k].values for k in ("open", "high", "low", "close"))
    a = df["atr"].values
    if i + 1 >= n or np.isnan(a[i]) or a[i] <= 0:
        return None
    entry = o[i + 1]
    if entry <= 0:
        return None
    d = 1
    stop = entry - d * STOP_ATR * a[i]
    tgt = entry + d * TARGET_ATR * a[i]
    for j in range(i + 1, min(i + 1 + MAX_HOLD, n)):
        if l[j] <= stop:
            return (stop - entry) / entry - SLIP * 2 - 2 * FEE
        if h[j] >= tgt:
            return (tgt - entry) / entry - SLIP * 2 - 2 * FEE
    ei = min(i + MAX_HOLD, n - 1)
    return (c[ei] - entry) / entry - SLIP * 2 - 2 * FEE


def boot_p(x: np.ndarray, n: int = 5000, seed: int = 7) -> float:
    """單尾 bootstrap p-value（H0: mean <= 0）。"""
    if len(x) < 5:
        return float("nan")
    rng = np.random.default_rng(seed)
    m = np.array([rng.choice(x, size=len(x), replace=True).mean() for _ in range(n)])
    return float((m <= 0).mean())


def main() -> None:
    rows = pd.read_csv(f"{OUT}/jev5_judgements.csv")
    rets = []
    cache: dict[str, pd.DataFrame] = {}
    for r in rows.itertuples():
        if r.tag not in cache:
            cache[r.tag] = add_rule_features(add_features(load_5m(r.tag), lookbacks=LOOKBACKS))
        rets.append(trade_return(cache[r.tag], int(r.i)))
    rows["ret"] = rets
    rows = rows.dropna(subset=["ret"])
    print(f"總計 {len(rows)} 筆附有報酬（Jev 判斷過的全部訊號）\n")

    # ── 核心檢定：setup 分桶 vs 實際報酬 ──
    print("=" * 78)
    print("核心檢定：「有矛盾的單是不是明顯比較虧？」")
    print("=" * 78)
    print(f"{'setup 桶':<14}{'n':>5}{'平均報酬%':>12}{'95% CI':>22}{'勝率':>8}{'p(mean<=0)':>12}")
    bucket_rows = []
    for lo, hi, name in [(0, 2.5, "0–2.5 模糊"), (2.5, 3.2, "2.5–3.2 弱"),
                         (3.2, 3.8, "3.2–3.8 中"), (3.8, 6, "3.8–5 清楚")]:
        b = rows[(rows["setup"] >= lo) & (rows["setup"] < hi)]
        if len(b) < 5:
            print(f"{name:<14}{len(b):>5}  樣本不足")
            continue
        x = b["ret"].values
        sd = x.std(ddof=1)
        lo_ci = x.mean() - 1.96 * sd / np.sqrt(len(x))
        hi_ci = x.mean() + 1.96 * sd / np.sqrt(len(x))
        p = boot_p(x)
        bucket_rows.append({"bucket": name, "n": len(x), "avg_pct": float(x.mean() * 100),
                            "ci_lo": float(lo_ci * 100), "ci_hi": float(hi_ci * 100),
                            "wr": float((x > 0).mean()), "p": p})
        print(f"{name:<14}{len(x):>5}{x.mean() * 100:>12.4f}"
              f"{f'[{lo_ci * 100:+.4f}, {hi_ci * 100:+.4f}]':>22}"
              f"{(x > 0).mean():>8.1%}{p:>12.3f}")

    # 單調性檢定：最低桶 vs 最高桶
    if len(bucket_rows) >= 2:
        lo_b = rows[rows["setup"] < 3.2]["ret"].values
        hi_b = rows[rows["setup"] >= 3.8]["ret"].values
        if len(lo_b) >= 5 and len(hi_b) >= 5:
            diff = hi_b.mean() - lo_b.mean()
            rng = np.random.default_rng(11)
            boot = np.array([rng.choice(hi_b, len(hi_b), replace=True).mean()
                             - rng.choice(lo_b, len(lo_b), replace=True).mean()
                             for _ in range(5000)])
            p_mono = float((boot <= 0).mean())
            print(f"\n低分組(<3.2, n={len(lo_b)}) vs 高分組(>=3.8, n={len(hi_b)}):")
            print(f"  平均 {lo_b.mean() * 100:+.4f}%  vs  {hi_b.mean() * 100:+.4f}%"
                  f"   差 {diff * 100:+.4f}%")
            print(f"  高分組較優的 bootstrap 機率 = {1 - p_mono:.3f}  "
                  f"({'顯著 ✓' if p_mono < 0.05 else '不顯著 ✗'})")

    # ── test 段：Jev 閘門 vs 隨機對照組（同通過率）──
    print("\n" + "=" * 78)
    print("test 段：Jev 閘門 vs 對照組（每筆只出現一次）")
    print("=" * 78)
    te = rows[rows["i"] >= rows["t2"]].copy()
    print(f"test 段共 {len(te)} 筆")

    def stats(x, name):
        if len(x) < 3:
            print(f"  {name:<32} n={len(x):>4}  樣本不足")
            return None
        x = np.asarray(x, dtype=float)
        sd = x.std(ddof=1)
        lo_ci = x.mean() - 1.96 * sd / np.sqrt(len(x))
        p = boot_p(x)
        print(f"  {name:<32} n={len(x):>4}  平均 {x.mean() * 100:+8.4f}%  "
              f"CI[{lo_ci * 100:+.4f}, {(x.mean() + 1.96 * sd / np.sqrt(len(x))) * 100:+.4f}]  "
              f"p={p:.3f}")
        return {"n": len(x), "avg_pct": float(x.mean() * 100), "p": p}

    e_mask = ((te["side"] == "BUY") & (te["p_buy"] >= 0.55) & (te["setup"] >= 3)
              & (te["p_not_trade"] < 0.3))
    out = {}
    out["A_規則本身"] = stats(te["ret"], "A 規則本身（無Jev）")
    out["B_BuySetup"] = stats(te[(te["side"] == "BUY") & (te["p_buy"] >= 0.55)
                                 & (te["setup"] >= 3)]["ret"], "B BUY且p>=.55且setup>=3")
    out["E_三原語"] = stats(te[e_mask]["ret"], "E 三原語全過")
    out["G_永遠HOLD"] = {"n": 0, "avg_pct": 0.0, "p": None}

    rng = np.random.default_rng(2026)
    n_keep = int(e_mask.sum())
    ctrl_means = []
    for _ in range(2000):
        pick = rng.choice(len(te), size=n_keep, replace=False)
        ctrl_means.append(te["ret"].values[pick].mean())
    ctrl = np.array(ctrl_means) * 100
    print(f"  {'F 隨機（同通過率，2000 次）':<32} n={n_keep:>4}  平均 {ctrl.mean():+8.4f}%"
          f"  ['{np.percentile(ctrl, 2.5):+.4f}, {np.percentile(ctrl, 97.5):+.4f}]'")
    if out["E_三原語"]:
        e_avg = out["E_三原語"]["avg_pct"]
        pct = float((ctrl >= e_avg).mean())
        print(f"\n  Jev 選的單比隨機好的機率 = {1 - pct:.3f}   "
              f"({'顯著 ✓' if pct < 0.05 else '不顯著 ✗'})")
        out["F_隨機"] = {"n": n_keep, "avg_pct": float(ctrl.mean()),
                         "p_beats_random": 1 - pct}

    json.dump({"buckets": bucket_rows, "test_gates": out},
              open(f"{OUT}/s5c_jev_stats.json", "w"), indent=2)
    print(f"\n-> {OUT}/s5c_jev_stats.json")


if __name__ == "__main__":
    main()
