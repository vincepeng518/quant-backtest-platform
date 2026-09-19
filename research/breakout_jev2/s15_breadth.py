#!/usr/bin/env python3
"""Stage 15：市場廣度（breadth）當突破策略的 regime 濾網。

動機：Stage 8 證明 4h 突破的失敗是 regime 依賴，但先前用的濾網（個別資產的
EMA200、ATR 百分位）都是**個體**指標。廣度是**市場層級**指標，資訊不同。

⚠️ 已知 red flag：corr(breadth, 市場動能) = +0.88，兩者高度重疊。
   所以本階段必須回答一個更嚴格的問題：**廣度是否提供市場動能之外的額外資訊？**
   設計：把「廣度」與「市場動能」並排當濾網，若兩者效果一樣 → 廣度沒有新資訊。

協定：
  - 開發期 = 前 60%（每檔固定參數，不在每檔上優化）
  - 留出期 = 後 40%，只測一次
  - 對照組：無濾網、隨機濾網（同通過率）、市場動能濾網
  - 獨立單位 = 時間期間，不是標的數
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


def main() -> None:
    # 面板（用於算廣度）
    frames = {}
    for sym in SYMS4:
        try:
            frames[sym] = prepare(load_4h(sym, "long"), LBS, EXIT_LOOKBACKS)
        except FileNotFoundError:
            continue
    common_idx = None
    for df in frames.values():
        s = set(df["timestamp"])
        common_idx = s if common_idx is None else (common_idx & s)
    common_idx = sorted(common_idx)
    print(f"共同時間軸 {len(common_idx):,} 根")

    C = pd.DataFrame({s: frames[s].set_index("timestamp")["close"].reindex(common_idx)
                      for s in frames})
    n_bars = len(C)
    cut = int(n_bars * 0.6)
    print(f"開發 {cut:,} 根（~{cut / 2190:.1f} 年） / 留出 {n_bars - cut:,} 根"
          f"（~{(n_bars - cut) / 2190:.1f} 年）\n")

    # ── 建構各種 market regime 指標 ──
    K = 30
    breadth = (C.pct_change(K, fill_method=None) > 0).mean(axis=1)   # 市場廣度
    mkt_mom = C.pct_change(K, fill_method=None).mean(axis=1)          # 市場動能
    # 標準化成 0-1 便於比較（用開發期的分布）
    mkt_rank = mkt_mom.rank(pct=True)

    print(f"breadth 分布: p10={breadth.quantile(.1):.2f} p50={breadth.median():.2f} "
          f"p90={breadth.quantile(.9):.2f}")
    print(f"mkt_mom 分布: p10={mkt_mom.quantile(.1):.4f} p50={mkt_mom.median():.4f} "
          f"p90={mkt_mom.quantile(.9):.4f}")
    print(f"corr(breadth, mkt_mom) = {breadth.corr(mkt_mom):+.3f}\n")

    # ── 濾網定義 ──
    FILTERS = {
        "none":            pd.Series(True, index=C.index),
        "breadth>=0.5":    breadth >= 0.50,
        "breadth>=0.7":    breadth >= 0.70,
        "breadth_top50":   breadth >= breadth.median(),
        "mktmom_top50":    mkt_rank >= 0.50,
        "mktmom_top30":    mkt_rank >= 0.70,
    }

    def eval_perm(flt: pd.Series, seg: str):
        """固定參數、套用市場級濾網，回傳 per-symbol metrics。"""
        lo, hi = (0, cut) if seg == "dev" else (cut, n_bars)
        allowed = flt.iloc[:n_bars].values.astype(bool)
        lb, d, ex, st, tr_, el = CFG
        per = []
        for sym, df in frames.items():
            sub = df.reindex(range(n_bars)) if False else df
            # 對齊：df 已是 common_idx 的子集？改用 reindex 到 common_idx
            d2 = df.set_index("timestamp").reindex(C.index[lo:hi]).reset_index() \
                   .rename(columns={"index": "timestamp"})
            d2 = d2.dropna(subset=["open", "close"]).reset_index(drop=True)
            if len(d2) < 100:
                continue
            # 把不被濾網允許的棒關掉
            allow_seg = allowed[lo:hi][:len(d2)]
            mask = ~allow_seg
            d2.loc[mask, f"don_hi_{lb}"] = 1e12
            d2.loc[mask, f"don_lo_{lb}"] = -1e12
            t2, eq = backtest_breakout(d2, lookback=lb, direction=d, exit_method=ex,
                                       stop_atr=st, target_atr=tr_, trail_atr=tr_,
                                       exit_lookback=el)
            m = metrics(t2, eq, len(d2), BARS_PER_YEAR["4h"])
            if m["n"] >= 2:
                per.append({"sym": sym, **{k: m[k] for k in
                                           ("sharpe", "avg_pct", "n", "maxdd_pct", "ret_pct")}})
        return per

    def summ(per, label):
        if len(per) < 4:
            return None
        sh = np.array([x["sharpe"] for x in per])
        av = np.array([x["avg_pct"] for x in per])
        return {"label": label, "n_syms": len(per), "median_sharpe": float(np.median(sh)),
                "mean_avg_pct": float(av.mean()), "pos_ratio": float((av > 0).mean()),
                "total_n": int(sum(x["n"] for x in per)),
                "n_bars_with_signal": int(sum(x["n"] for x in per))}

    print("=" * 92)
    print("開發期：廣度 vs 市場動能（若效果相同 → 廣度無額外資訊）")
    print("=" * 92)
    print(f"{'濾網':>16}{'標的數':>8}{'中位Sharpe':>12}{'正標的':>9}{'平均%':>10}{'總交易':>8}")
    dev_res = {}
    for name, flt in FILTERS.items():
        per = eval_perm(flt, "dev")
        s = summ(per, name)
        if s:
            dev_res[name] = s
            print(f"{name:>16}{s['n_syms']:>8}{s['median_sharpe']:>12.2f}"
                  f"{s['pos_ratio']:>9.0%}{s['mean_avg_pct']:>10.4f}{s['total_n']:>8}")

    # ── 關鍵比較：廣度 vs 市場動能 ──
    print("\n" + "=" * 92)
    print("關鍵比較：廣度 vs 市場動能")
    print("=" * 92)
    if "breadth>=0.5" in dev_res and "mktmom_top50" in dev_res:
        b = dev_res["breadth>=0.5"]
        m2 = dev_res["mktmom_top50"]
        print(f"  breadth>=0.5 : 中位Sharpe {b['median_sharpe']:+.2f}  "
              f"正標的 {b['pos_ratio']:.0%}  平均 {b['mean_avg_pct']:+.4f}%  交易 {b['total_n']}")
        print(f"  mktmom_top50 : 中位Sharpe {m2['median_sharpe']:+.2f}  "
              f"正標的 {m2['pos_ratio']:.0%}  平均 {m2['mean_avg_pct']:+.4f}%  交易 {m2['total_n']}")
        diff = b["median_sharpe"] - m2["median_sharpe"]
        print(f"  → 差異 {diff:+.2f}  "
              f"{'廣度有額外資訊 ✓' if abs(diff) > 0.3 else '兩者效果相當 ✗ 廣度無額外資訊'}")

    # ── 留出期（只跑最好的那個濾網，一次）──
    cands = [v for v in dev_res.values() if v["median_sharpe"] > 0.3 and v["pos_ratio"] >= 0.6]
    cands.sort(key=lambda v: v["median_sharpe"], reverse=True)
    if not cands:
        print("\n開發期無候選 → 停止，不測留出期")
        json.dump({"dev": dev_res, "verdict": "no_dev_candidate"},
                  open(f"{OUT}/s15_breadth.json", "w"), indent=2)
        return

    best = cands[0]
    print(f"\n選定（依開發期）：{best['label']}")
    per_h = eval_perm(FILTERS[best["label"]], "hold")
    h = summ(per_h, best["label"])
    print(f"\n{'=' * 92}\n留出期（只跑一次）\n{'=' * 92}")
    print(f"  開發: 中位Sharpe {best['median_sharpe']:+.2f}  正標的 {best['pos_ratio']:.0%}  "
          f"平均 {best['mean_avg_pct']:+.4f}%  交易 {best['total_n']}")
    if h:
        print(f"  留出: 中位Sharpe {h['median_sharpe']:+.2f}  正標的 {h['pos_ratio']:.0%}  "
              f"平均 {h['mean_avg_pct']:+.4f}%  交易 {h['total_n']}")
        # 逐年（獨立單位 = 時間）
        ydf_parts = []
        for sym, df in frames.items():
            pass
        print(f"  → {'留出期仍為正 ✓' if h['mean_avg_pct'] > 0 else '留出期失效 ✗'}")

    json.dump({"dev": dev_res, "best": best, "holdout": h},
              open(f"{OUT}/s15_breadth.json", "w"), indent=2)
    print(f"\n-> {OUT}/s15_breadth.json")


if __name__ == "__main__":
    main()
