#!/usr/bin/env python3
"""Stage 11：誠實檢驗 Stage 10 唯一存活的候選（trail_both_lb192）。

Stage 10 用了「182 個標的橫斷面 bootstrap，p=0.0254」。但這有兩個嚴重問題：
  1. **獨立性假設被違反**：182 檔的留出期是同一段日曆時間，加密貨幣彼此高度相關
     → 有效樣本數遠小於 182，p 值被嚴重低估
  2. **多重比較**：同時測了 5 個配置，Bonferroni 門檻是 0.05/5 = 0.01
     → p=0.0254 過不了

本階段做三項修正檢定：
  A. 時間分塊一致性：把留出期切成 4 段，每段是否都為正
  B. 標的集中度：獲利是否集中在少數幾檔（若是，則不是普遍 edge）
  C. 有效獨立樣本數估計：用標的間報酬相關矩陣估 n_eff，重算 p 值
"""
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/root/Crypto-Backtesting-Lab")
from research.breakout_jev2.lib_breakout import backtest_breakout, metrics, prepare
from research.breakout_jev2.lib_data_multi import BARS_PER_YEAR

OUT = "/root/Crypto-Backtesting-Lab/runtime/breakout_jev2"
EXIT_LOOKBACKS = [12, 24, 48, 96]
LBS = [24, 48, 96, 192]
MIN_BARS = 2500
CFG = (192, "both", "trail", 2.5, 3.0, 48)


def load_okx_4h(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df[["timestamp", "open", "high", "low", "close", "volume"]] \
             .dropna().sort_values("timestamp").reset_index(drop=True)


def main() -> None:
    files = sorted(glob.glob("/root/okx_data/*_4h.csv"))
    frames = {}
    for p in files:
        sym = os.path.basename(p)[:-7]
        try:
            df = load_okx_4h(p)
        except Exception:
            continue
        if len(df) >= MIN_BARS:
            frames[sym] = prepare(df, LBS, EXIT_LOOKBACKS)
    print(f"標的 {len(frames)} 檔")

    lb, d, ex, st, tr_, el = CFG
    print(f"候選配置 {CFG}\n")

    # 收集每檔的（逐筆交易報酬, 交易時間）
    per_sym = {}
    for sym, df in frames.items():
        n = len(df)
        cut = int(n * 0.6)
        t, eq = backtest_breakout(df, lookback=lb, direction=d, exit_method=ex,
                                  stop_atr=st, target_atr=tr_, trail_atr=tr_,
                                  exit_lookback=el, start=cut, end=n)
        if len(t) >= 3:
            per_sym[sym] = {"trades": t, "idx": [x["i"] for x in t],
                            "rets": np.array([x["ret"] for x in t]),
                            "ts": [pd.Timestamp(x["ts_entry"]) for x in t],
                            "metrics": metrics(t, eq, n - cut, BARS_PER_YEAR["4h"])}
    print(f"留出期有交易者 {len(per_sym)} 檔，總交易 "
          f"{sum(len(v['trades']) for v in per_sym.values())}")

    all_avg = np.array([v["metrics"]["avg_pct"] for v in per_sym.values()])
    print(f"橫斷面平均 {all_avg.mean():+.4f}%  中位 {np.median(all_avg):+.4f}%  "
          f"正標的 {np.mean(all_avg > 0):.0%}\n")

    # ═══ A. 時間分塊一致性 ═══
    print("=" * 88)
    print("A. 時間分塊一致性（把留出期切成 4 段，每段獨立看）")
    print("=" * 88)
    alloc = []
    for sym, v in per_sym.items():
        for ts, r in zip(v["ts"], v["rets"]):
            alloc.append((ts, r))
    adf = pd.DataFrame(alloc, columns=["ts", "ret"]).sort_values("ts")
    adf["bucket"] = pd.qcut(adf["ts"], 4, labels=False)
    print(f"{'段':>4}{'期間':>26}{'筆數':>8}{'平均%':>11}{'勝率':>8}")
    seg_stats = []
    for b in range(4):
        sub = adf[adf["bucket"] == b]
        seg_stats.append(float(sub["ret"].mean() * 100))
        print(f"{b:>4}{f'{sub.ts.min().date()} ~ {sub.ts.max().date()}':>26}"
              f"{len(sub):>8}{sub['ret'].mean() * 100:>11.4f}{(sub['ret'] > 0).mean():>8.1%}")
    pos_segs = sum(1 for x in seg_stats if x > 0)
    print(f"→ {pos_segs}/4 段為正  {'一致 ✓' if pos_segs == 4 else '不一致 ✗'}")

    # ═══ B. 標的集中度 ═══
    print("\n" + "=" * 88)
    print("B. 標的集中度：獲利是否集中在少數幾檔")
    print("=" * 88)
    tot = sum(v["rets"].sum() for v in per_sym.values())
    contrib = sorted(((sym, v["rets"].sum() / tot) for sym, v in per_sym.items()),
                     key=lambda x: -x[1])
    print(f"總報酬單位 {tot:.2f}")
    print(f"  前 5 檔貢獻: {', '.join(f'{s} {c:.1%}' for s, c in contrib[:5])}")
    print(f"  前 10 檔貢獻合計: {sum(c for _, c in contrib[:10]):.1%}")
    print(f"  最差 5 檔: {', '.join(f'{s} {c:.1%}' for s, c in contrib[-5:])}")
    top10 = sum(c for _, c in contrib[:10])
    print(f"→ 前 10 檔佔 {top10:.0%} 的總獲利  "
          f"{'集中（不是普遍 edge）✗' if top10 > 0.5 else '分散 ✓'}")

    # ═══ C. 有效獨立樣本數（時段相關性修正）═══
    print("\n" + "=" * 88)
    print("C. 有效獨立樣本數修正：標的間高度相關 → p 值被低估")
    print("=" * 88)
    # 把留出期切成月，算每檔的月度平均報酬 → 標的間相關
    adf["month"] = adf["ts"].dt.to_period("M").astype(str)
    piv = adf.pivot_table(index="month", columns="ts", values="ret", aggfunc="mean")
    mtx = {}
    for sym, v in per_sym.items():
        cols = [c for c in adf.columns if c == "ts"]
    # 以標的為欄重做
    recs = []
    for sym, v in per_sym.items():
        for ts, r in zip(v["ts"], v["rets"]):
            recs.append({"month": ts.strftime("%Y-%m"), "sym": sym, "ret": r})
    rdf = pd.DataFrame(recs)
    pv = rdf.pivot_table(index="month", columns="sym", values="ret", aggfunc="mean")
    pv = pv.dropna(axis=1, thresh=max(3, int(len(pv) * 0.5)))
    print(f"月度 × 標的矩陣: {pv.shape[0]} 個月 × {pv.shape[1]} 檔")
    if pv.shape[1] >= 5 and pv.shape[0] >= 5:
        corm = pv.corr(min_periods=3).values
        iu = np.triu_indices_from(corm, k=1)
        valid = corm[iu][~np.isnan(corm[iu])]
        mean_rho = float(np.mean(valid)) if len(valid) else float("nan")
        print(f"  標的間月度報酬平均相關 ρ = {mean_rho:.3f}")
        # 平均相關下的有效樣本數（簡化：n_eff = N / (1 + (N-1)*rho)）
        N = len(all_avg)
        n_eff = N / (1 + (N - 1) * max(mean_rho, 0))
        print(f"  名目樣本 {N} 檔 → 有效獨立樣本 n_eff ≈ {n_eff:.1f}")
        sd = all_avg.std(ddof=1)
        t_naive = all_avg.mean() / (sd / np.sqrt(N))
        t_eff = all_avg.mean() / (sd / np.sqrt(max(n_eff, 1)))
        # 單尾 p（t 分布近似）
        from scipy import stats as _st  # noqa
        p_naive = 1 - _st.t.cdf(t_naive, df=N - 1)
        p_eff = 1 - _st.t.cdf(t_eff, df=max(n_eff - 1, 1))
        print(f"  名目 t={t_naive:.2f}  p={p_naive:.4f}")
        print(f"  修正 t={t_eff:.2f}  p_eff={p_eff:.4f}")
        print(f"  Bonferroni 門檻（5 個配置）= 0.0100")
        verdict = "通過" if p_eff < 0.01 else "不通過"
        print(f"→ 修正後 {'✓' if p_eff < 0.01 else '✗'} {verdict}")

    # ═══ 結論 ═══
    print("\n" + "=" * 88)
    print("結論")
    print("=" * 88)
    ok_a = pos_segs == 4
    ok_b = top10 <= 0.5
    print(f"A 時間一致性: {pos_segs}/4 → {'通過' if ok_a else '不通過'}")
    print(f"B 標的分散度: 前10檔 {top10:.0%} → {'通過' if ok_b else '不通過'}")
    print(f"C 相關性修正 p: {'見上' if pv.shape[1] >= 5 else '矩陣太小無法計算'}")

    json.dump({
        "config": list(CFG), "n_syms": len(per_sym),
        "cross_section_mean_pct": float(all_avg.mean()),
        "cross_section_median_pct": float(np.median(all_avg)),
        "pos_ratio": float(np.mean(all_avg > 0)),
        "segment_means_pct": seg_stats, "pos_segments": pos_segs,
        "top10_contribution": float(top10),
        "mean_rho": float(mean_rho) if pv.shape[1] >= 5 else None,
    }, open(f"{OUT}/s11_honest_check.json", "w"), indent=2)
    print(f"\n-> {OUT}/s11_honest_check.json")


if __name__ == "__main__":
    main()
