#!/usr/bin/env python3
"""Stage 14：聚合檢定 —— 驗證「7/7 標的都高於 null 平均」是真訊號還是假象。

Stage 13 的 C 顯示：單檔置換檢定 0/7 顯著，但 7/7 的觀測值都高於 null 平均。
單檔 p 值不顯著 ≠ 沒有訊號 —— 可能是每檔樣本太小（n=30-38）。
正確做法是**聚合**：把所有標的的交易併成一個投資組合，再跟同樣聚合的 null 比。

三項檢定：
  1. 組合層級置換檢定：7 檔等權組合的 Sharpe vs 300 次「全體隨機進場」的組合 Sharpe
  2. 符號檢定：7/7 高於 null 中位數的機率（考慮相關性後修正）
  3. 多空分解：這個「高於隨機」的來源是多腿還是空腿？（可能是多頭偏誤，不是 alpha）
"""
import json
import sys

import numpy as np

sys.path.insert(0, "/root/Crypto-Backtesting-Lab")
from research.breakout_jev2.lib_breakout import backtest_breakout, metrics, prepare
from research.breakout_jev2.lib_data_multi import BARS_PER_YEAR, load_4h

OUT = "/root/Crypto-Backtesting-Lab/runtime/breakout_jev2"
EXIT_LOOKBACKS = [12, 24, 48, 96]
LBS = [24, 48, 96, 192]
SYMS4 = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT", "XRPUSDT"]
CFG = (96, "both", "donchian", 4.0, 3.0, 96)
N_PERM = 300


def portfolio_sharpe(all_rets: list[np.ndarray], bars: int, bars_per_year: float,
                     hold: float = 24.0) -> float:
    """7 檔等權組合：先算每檔的平均報酬，再對這 7 個平均做統計。

    這是「投資組合層級」的檢定，獨立單位是標的（但相關性仍需注意）。
    """
    means = np.array([r.mean() for r in all_rets if len(r) > 0])
    if len(means) < 3:
        return 0.0
    sd = means.std(ddof=1)
    return float(means.mean() / sd * np.sqrt(len(means))) if sd > 0 else 0.0


def main() -> None:
    report = {}
    lb, d, ex, st, tr_, el = CFG
    frames = {}
    for sym in SYMS4:
        try:
            frames[sym] = prepare(load_4h(sym, "long"), LBS, EXIT_LOOKBACKS)
        except FileNotFoundError:
            continue

    def run_all(random: bool, seed: int = 2026):
        """回傳 {sym: (rets, dirs)}。random=True 時用隨機進場點。"""
        rng = np.random.default_rng(seed)
        out = {}
        for sym, df in frames.items():
            n = len(df)
            cut = int(n * 0.75)
            if random:
                # 先取得實際交易數
                t0, _ = backtest_breakout(df, lookback=lb, direction=d, exit_method=ex,
                                          stop_atr=st, target_atr=tr_, trail_atr=tr_,
                                          exit_lookback=el, start=cut, end=n)
                k = max(3, len(t0))
                pick = rng.choice(np.arange(cut, n - 200), size=k, replace=False)
                d2 = df.copy()
                # 先把「所有」棒關掉，再讓挑中的棒**強制觸發**：
                # 隨機棒原本不一定符合突破條件，只關其他棒會導致幾乎零交易
                d2[f"don_hi_{lb}"] = 1e12
                d2[f"don_lo_{lb}"] = -1e12
                d2.loc[d2.index[pick], f"don_hi_{lb}"] = d2["close"].values[pick] * 0.999
                d2.loc[d2.index[pick], f"don_lo_{lb}"] = d2["close"].values[pick] * 1.001
                t2, _ = backtest_breakout(d2, lookback=lb, direction=d, exit_method=ex,
                                          stop_atr=st, target_atr=tr_, trail_atr=tr_,
                                          exit_lookback=el, start=cut, end=n)
            else:
                t2, _ = backtest_breakout(df, lookback=lb, direction=d, exit_method=ex,
                                          stop_atr=st, target_atr=tr_, trail_atr=tr_,
                                          exit_lookback=el, start=cut, end=n)
            if len(t2) < 3:
                continue
            out[sym] = (np.array([x["ret"] for x in t2]),
                        np.array([x["dir"] for x in t2]))
        return out

    # ── 觀測 ──
    obs = run_all(random=False)
    print("=" * 88)
    print("觀測：各標的交易數與平均報酬")
    print("=" * 88)
    for sym, (r, dr) in obs.items():
        print(f"  {sym:>10}  n={len(r):>3}  平均 {r.mean() * 100:+.4f}%  "
              f"多 {np.sum(dr > 0):>3} 筆 / 空 {np.sum(dr < 0):>3} 筆")
    obs_means = np.array([r.mean() for r, _ in obs.values()])
    obs_pf_sh = portfolio_sharpe([r for r, _ in obs.values()], 0, BARS_PER_YEAR["4h"])
    print(f"\n  組合等權平均 {obs_means.mean() * 100:+.4f}%  "
          f"組合 Sharpe（跨 7 檔） {obs_pf_sh:+.2f}")

    # ── 檢定 1：組合層級置換 ──
    print("\n" + "=" * 88)
    print(f"檢定 1：組合層級置換（{N_PERM} 次全體隨機進場）")
    print("=" * 88)
    null_mean_sh = []
    null_means = []
    for i in range(N_PERM):
        rnd = run_all(random=True, seed=1000 + i)
        if len(rnd) < 4:
            continue
        null_mean_sh.append(portfolio_sharpe([r for r, _ in rnd.values()], 0,
                                             BARS_PER_YEAR["4h"]))
        null_means.append(np.mean([r.mean() for r, _ in rnd.values()]))
    null_mean_sh = np.array(null_mean_sh)
    null_means = np.array(null_means)
    if len(null_mean_sh) >= 50:
        p_sh = float((null_mean_sh >= obs_pf_sh).mean())
        p_mean = float((null_means >= obs_means.mean()).mean())
        print(f"  null 組合 Sharpe: 平均 {null_mean_sh.mean():+.2f}  "
              f"P50 {np.percentile(null_mean_sh, 50):+.2f}  "
              f"P95 {np.percentile(null_mean_sh, 95):+.2f}")
        print(f"  觀測組合 Sharpe: {obs_pf_sh:+.2f}   p={p_sh:.3f}  "
              f"{'顯著 ✓' if p_sh < 0.05 else '不顯著 ✗'}")
        print(f"  null 組合平均報酬: 平均 {null_means.mean() * 100:+.4f}%  "
              f"P95 {np.percentile(null_means, 95) * 100:+.4f}%")
        print(f"  觀測組合平均: {obs_means.mean() * 100:+.4f}%   p={p_mean:.3f}  "
              f"{'顯著 ✓' if p_mean < 0.05 else '不顯著 ✗'}")
        report["portfolio_permutation"] = {
            "obs_sharpe": obs_pf_sh, "obs_mean_pct": float(obs_means.mean() * 100),
            "null_sharpe_mean": float(null_mean_sh.mean()),
            "null_sharpe_p95": float(np.percentile(null_mean_sh, 95)),
            "p_sharpe": p_sh, "p_mean": p_mean, "n_null": len(null_mean_sh)}

    # ── 檢定 2：符號檢定 ──
    print("\n" + "=" * 88)
    print("檢定 2：符號檢定（7/7 高於 null 中位數）")
    print("=" * 88)
    if len(null_means) >= 50:
        from scipy import stats as stt
        # 每檔觀測值 vs null 中位數
        obs_vs = [r.mean() * 100 for r, _ in obs.values()]
        n_above = sum(1 for v in obs_vs if v > np.median(null_means) * 100)
        n_tot = len(obs_vs)
        p_sign = float(stt.binomtest(n_above, n_tot, 0.5, alternative="greater").pvalue)
        print(f"  {n_above}/{n_tot} 檔觀測值高於 null 中位數")
        print(f"  符號檢定 p={p_sign:.4f}  {'顯著 ✓' if p_sign < 0.05 else '不顯著 ✗'}")
        print(f"  ⚠️ 注意：7 檔加密貨幣高度相關，符號檢定會**高估**顯著性")
        report["sign_test"] = {"n_above": n_above, "n_total": n_tot, "p": p_sign}

    # ── 檢定 3：多空分解 ──
    print("\n" + "=" * 88)
    print("檢定 3：多空分解 —— 「高於隨機」是 alpha 還是多頭偏誤？")
    print("=" * 88)
    print(f"{'標的':>10}{'多筆數':>8}{'多平均%':>11}{'空筆數':>8}{'空平均%':>11}{'買進持有%':>12}")
    long_all, short_all = [], []
    for sym, (r, dr) in obs.items():
        lr = r[dr > 0]
        sr = r[dr < 0]
        long_all.append(lr.mean() if len(lr) else 0.0)
        short_all.append(sr.mean() if len(sr) else 0.0)
        c = frames[sym]["close"].values
        n = len(frames[sym])
        cut = int(n * 0.75)
        bhr = (c[-1] / c[cut] - 1) * 100
        print(f"{sym:>10}{len(lr):>8}{lr.mean() * 100 if len(lr) else 0:>11.4f}"
              f"{len(sr):>8}{sr.mean() * 100 if len(sr) else 0:>11.4f}{bhr:>12.1f}")
    long_all = np.array(long_all)
    short_all = np.array(short_all)
    print(f"\n  多腿組合平均 {long_all.mean() * 100:+.4f}%   "
          f"空腿組合平均 {short_all.mean() * 100:+.4f}%")
    print(f"  → {'多腿貢獻主要報酬' if long_all.mean() > abs(short_all.mean()) else '空腿貢獻主要報酬'}")
    # 檢驗：多腿是否只是「買進持有」的代理
    bh_means = np.array([(frames[s]["close"].values[-1] / frames[s]["close"].values[int(len(frames[s]) * 0.75)] - 1)
                         for s in obs])
    corr_lb = float(np.corrcoef(long_all, bh_means)[0, 1]) if len(long_all) > 2 else float("nan")
    print(f"  corr(多腿平均, 買進持有) = {corr_lb:+.2f}  "
          f"{'→ 多腿只是買進持有的代理（不是 alpha）' if corr_lb > 0.7 else '→ 多腿與買進持有不同'}")
    report["long_short"] = {"long_mean_pct": float(long_all.mean() * 100),
                            "short_mean_pct": float(short_all.mean() * 100),
                            "corr_long_vs_bh": corr_lb}

    json.dump(report, open(f"{OUT}/s14_aggregate.json", "w"), indent=2)
    print(f"\n-> {OUT}/s14_aggregate.json")


if __name__ == "__main__":
    main()
