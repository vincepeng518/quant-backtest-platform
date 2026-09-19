#!/usr/bin/env python3
"""Stage 12：橫斷面策略搜尋（突破 × 相對強弱）。

為什麼這條路能避開 Stage 10 的死亡陷阱：
  Stage 10 失敗在「182 檔的留出期是同一段日曆時間、彼此相關」，
  用標的數當獨立樣本量 → n_eff 只剩 12.2，p 值假性顯著。
  橫斷面策略是多空價差（做多強的、做空弱的），相關的市場成分在兩腿互相抵消。
  **統計檢定的獨立單位改用時間期間（月），不是標的數。**

策略族：
  CS_MOM       純橫斷面動能：做多最強 q 檔、做空最弱 q 檔，固定持倉 N 根
  BRK_CS       突破 × 相對強弱：只做多「突破且動能排名前 q」、做空「跌破且排名後 q」
  BRK_CS_SQ    上一族 + 盤整壓縮前置條件
  對照組：
  BRK_TS       純時間序列突破（前面已證失敗，做為基準）
  CS_MOM_RAND  隨機選股（同檔數）→ 檢驗排序是否有資訊
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "/root/Crypto-Backtesting-Lab")
from research.breakout_jev2.lib_panel import (
    breakout_mask, build_panel, cross_sectional_momentum_signal, drop_short_history,
    squeeze_mask,
)

OUT = "/root/Crypto-Backtesting-Lab/runtime/breakout_jev2"
os.makedirs(OUT, exist_ok=True)
FEE = 0.0005
SLIP = 0.0002
COST = 2 * (FEE + SLIP)          # 每次進出一趟的總成本（比例）


def panel_returns(C: pd.DataFrame, O: pd.DataFrame, hold: int) -> pd.DataFrame:
    """第 t 根收盤做決策 → 第 t+1 根開盤進場 → 持 hold 根後開盤出場的報酬。"""
    entry = O.shift(-1)
    exit_ = O.shift(-1 - hold)
    return (exit_ / entry) - 1.0


def run_cs(
    C: pd.DataFrame, O: pd.DataFrame, H: pd.DataFrame, L: pd.DataFrame,
    *, hold: int = 24, lookback: int = 96, top_q: float = 0.2,
    use_breakout: bool = False, use_squeeze: bool = False,
    use_momentum_rank: bool = True, random_select: bool = False,
    min_universe: int = 20, seed: int = 7,
):
    """橫斷面多空回測。回傳 per-period 的投資組合報酬序列與診斷。

    每個期間的報酬 =（多腿平均報酬 − 空腿平均報酬）/ 2 − 成本
    （/2 是讓多空各半資金，總曝險 = 1）

    只在**多空兩腿都有交易**的期間才記錄報酬；沒訊號的期間直接跳過
    （不記 0，否則會把「不交易」當成低波動而高估 Sharpe）。
    """
    n = len(C)
    ret = panel_returns(C, O, hold)
    idx = C.index

    if random_select:
        rng = np.random.default_rng(seed)
        ranks = pd.DataFrame(rng.random((n, C.shape[1])), index=idx, columns=C.columns)
        k = max(1, int(round(C.shape[1] * top_q)))
        lon_v = pd.DataFrame(False, index=idx, columns=C.columns)
        sho_v = pd.DataFrame(False, index=idx, columns=C.columns)
        for t in range(n):
            order = ranks.iloc[t].sort_values(ascending=False)
            lon_v.iloc[t, [C.columns.get_loc(s) for s in order.index[:k]]] = True
            sho_v.iloc[t, [C.columns.get_loc(s) for s in order.index[-k:]]] = True
        lon_v = lon_v & C.notna()
        sho_v = sho_v & C.notna()
    else:
        lon_v, sho_v = cross_sectional_momentum_signal(
            C, lookback, top_q=top_q, bottom_q=top_q, min_universe=min_universe)

    if use_breakout:
        bk = breakout_mask(C, H, lookback)
        bk_dn = C < L.rolling(lookback).min().shift(1)
        lon_v = lon_v & bk
        sho_v = sho_v & bk_dn
    elif not random_select:
        # 純橫斷面動能：每天重選，但只在排名變動時換倉（用 hold 間隔控制換手）
        pass

    if use_squeeze:
        sq = squeeze_mask(C)
        lon_v = lon_v & sq
        sho_v = sho_v & sq

    periods = []
    t = lookback + 20
    while t < n - hold - 2:
        lo = lon_v.iloc[t]
        sh = sho_v.iloc[t]
        n_long = int(lo.sum())
        n_short = int(sh.sum())
        if n_long == 0 or n_short == 0:
            # 沒訊號 = 不交易。**不記為 0 報酬**：那會把「不交易」當成低波動，
            # 用這種序列算 Sharpe 會嚴重高估（實測勝率 0.4% 就是這個病的症狀）。
            t += hold
            continue
        r = ret.iloc[t]
        long_r = r[lo.values].mean()
        short_r = r[sh.values].mean()
        gross = (long_r - short_r) / 2.0
        net = gross - COST
        periods.append({"t": idx[t], "ret": float(net), "gross": float(gross),
                        "n_long": n_long, "n_short": n_short})
        t += hold

    pdf = pd.DataFrame(periods)
    return pdf


def summarize(pdf: pd.DataFrame, label: str, bars_per_year: float = 2190.0,
              hold: int = 24) -> dict:
    if pdf is None or len(pdf) == 0 or "ret" not in pdf.columns:
        return {"label": label, "n": 0, "mean_pct": 0.0, "median_pct": 0.0, "wr": 0.0,
                "sharpe": 0.0, "ret_pct": 0.0, "maxdd_pct": 0.0, "t_stat": 0.0,
                "insufficient": True}
    r = pdf["ret"].values.astype(float)
    r = r[~np.isnan(r)]
    if len(r) == 0:
        return {"label": label, "n": 0, "mean_pct": 0.0, "median_pct": 0.0, "wr": 0.0,
                "sharpe": 0.0, "ret_pct": 0.0, "maxdd_pct": 0.0, "t_stat": 0.0,
                "insufficient": True}
    sd = r.std(ddof=1) if len(r) > 1 else 0.0
    per_year = bars_per_year / hold
    sharpe = float(r.mean() / sd * np.sqrt(per_year)) if sd > 0 else 0.0
    eq = np.cumprod(1 + r)
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    return {"label": label, "n": len(r), "mean_pct": float(r.mean() * 100),
            "median_pct": float(np.median(r) * 100), "wr": float((r > 0).mean()),
            "sharpe": sharpe, "ret_pct": float((eq[-1] - 1) * 100),
            "maxdd_pct": float(dd.min() * 100),
            "t_stat": float(r.mean() / (sd / np.sqrt(len(r)))) if sd > 0 else 0.0}


def main() -> None:
    t0 = time.perf_counter()
    print("建構 4h 面板…", flush=True)
    C, H, L, O = build_panel("4h", min_bars=2500, min_universe_count=20)
    C, H, L, O = drop_short_history(C, H, L, O, min_obs_frac=0.85)
    print(f"  面板 {C.shape[0]:,} 根 × {C.shape[1]} 檔  "
          f"{C.index[0].date()} ~ {C.index[-1].date()}\n")

    # 時間分割：前 60% 開發、後 40% 留出
    n = len(C)
    cut = int(n * 0.6)
    print(f"開發 前60% = {cut:,} 根（~{cut / 2190:.1f} 年） / "
          f"留出 後40% = {n - cut:,} 根（~{(n - cut) / 2190:.1f} 年）\n")

    results = []
    CONFIGS = [
        # (label, kwargs)
        ("CS_MOM_q20_h24",   dict(lookback=96, top_q=0.20, hold=24)),
        ("CS_MOM_q20_h72",   dict(lookback=96, top_q=0.20, hold=72)),
        ("CS_MOM_q10_h24",   dict(lookback=96, top_q=0.10, hold=24)),
        ("CS_MOM_lb384_h24", dict(lookback=384, top_q=0.20, hold=24)),
        ("BRK_CS_q20_h24",   dict(lookback=96, top_q=0.20, hold=24, use_breakout=True)),
        ("BRK_CS_q20_h72",   dict(lookback=96, top_q=0.20, hold=72, use_breakout=True)),
        ("BRK_CS_q30_h24",   dict(lookback=96, top_q=0.30, hold=24, use_breakout=True)),
        ("BRK_CS_SQ_q20_h24", dict(lookback=96, top_q=0.20, hold=24, use_breakout=True,
                                   use_squeeze=True)),
        ("RANDOM_q20_h24",   dict(lookback=96, top_q=0.20, hold=24, random_select=True)),
    ]

    print("=" * 92)
    print("開發期（前 60%）")
    print("=" * 92)
    print(f"{'策略':>20}{'n':>6}{'每期平均%':>11}{'勝率':>8}{'Sharpe':>9}{'t':>7}{'總報酬%':>11}{'MaxDD%':>9}")
    for label, kw in CONFIGS:
        pdf = run_cs(C, O, H, L, **kw)
        if len(pdf) == 0 or "t" not in pdf.columns:
            s = summarize(pdf, label, hold=kw.get("hold", 24))
            s["hold"] = kw.get("hold", 24)
            s["kwargs"] = {k: v for k, v in kw.items() if k != "seed"}
            results.append(s)
            print(f"{label:>20}{0:>6}{'（無有效訊號）':>20}")
            continue
        dev = pdf[pdf["t"] < C.index[cut]]
        s = summarize(dev, label, hold=kw.get("hold", 24))
        s["hold"] = kw.get("hold", 24)
        s["kwargs"] = {k: v for k, v in kw.items() if k != "seed"}
        results.append(s)
        print(f"{label:>20}{s['n']:>6}{s['mean_pct']:>11.4f}{s['wr']:>8.1%}"
              f"{s['sharpe']:>9.2f}{s['t_stat']:>7.2f}{s['ret_pct']:>11.1f}{s['maxdd_pct']:>9.1f}")

    # 選開發期最佳（t 統計最大），但要求 n >= 30
    cands = [r for r in results if r["n"] >= 30 and r["mean_pct"] > 0 and not r.get("insufficient")]
    cands.sort(key=lambda r: r["t_stat"], reverse=True)
    print(f"\n開發期合格候選（n>=30 且平均為正）：{len(cands)}")
    for r in cands[:5]:
        print(f"  {r['label']:>20}  t={r['t_stat']:+.2f}  平均 {r['mean_pct']:+.4f}%  "
              f"Sharpe {r['sharpe']:+.2f}  n={r['n']}")

    if not cands:
        print("\n開發期就沒有任何候選 -> 停止，不再測留出期")
        json.dump({"dev": results}, open(f"{OUT}/s12_cross_sectional.json", "w"), indent=2)
        return

    best = cands[0]
    print(f"\n選定（依開發期 t 統計）：{best['label']}  {best['kwargs']}")

    # ── 留出期只跑一次 ──
    print("\n" + "=" * 92)
    print(f"留出期（後 40%）—— 只跑一次")
    print("=" * 92)
    kw = dict(best["kwargs"])
    pdf = run_cs(C, O, H, L, **kw)
    hold_dev = pdf[pdf["t"] < C.index[cut]]
    hold_out = pdf[pdf["t"] >= C.index[cut]]
    s_dev = summarize(hold_dev, best["label"], hold=kw.get("hold", 24))
    s_ho = summarize(hold_out, best["label"], hold=kw.get("hold", 24))
    print(f"  開發段:   n={s_dev['n']:>4}  平均 {s_dev['mean_pct']:+.4f}%  "
          f"Sharpe {s_dev['sharpe']:+.2f}  t={s_dev['t_stat']:+.2f}")
    print(f"  留出段:   n={s_ho['n']:>4}  平均 {s_ho['mean_pct']:+.4f}%  "
          f"Sharpe {s_ho['sharpe']:+.2f}  t={s_ho['t_stat']:+.2f}  "
          f"勝率 {s_ho['wr']:.1%}  總報酬 {s_ho['ret_pct']:+.1f}%  MaxDD {s_ho['maxdd_pct']:.1f}%")

    # ── 留出期逐年（獨立單位 = 時間）──
    print(f"\n  留出期逐年（獨立單位 = 年，不是標的數）：")
    hold_out = hold_out.copy()
    hold_out["year"] = pd.to_datetime(hold_out["t"]).dt.year
    yearly = hold_out.groupby("year")["ret"].agg(["mean", "count"])
    for y, row in yearly.iterrows():
        print(f"    {y}: n={int(row['count']):>3}  平均 {row['mean'] * 100:+.4f}%  "
              f"{'正' if row['mean'] > 0 else '負'}")
    pos_years = int((yearly["mean"] > 0).sum())
    print(f"  → {pos_years}/{len(yearly)} 年為正")

    # 逐年 bootstrap（以年為獨立單位重抽）
    if len(yearly) >= 4:
        yr_means = yearly["mean"].values
        rng = np.random.default_rng(11)
        boot = np.array([rng.choice(yr_means, len(yr_means), replace=True).mean()
                         for _ in range(5000)])
        p = float((boot <= 0).mean())
        print(f"  以「年」為獨立單位的 bootstrap: 平均 {yr_means.mean() * 100:+.4f}%  "
              f"p(mean<=0)={p:.3f}  {'顯著 ✓' if p < 0.05 else '不顯著 ✗'}")

    json.dump({"dev": results, "best": best, "holdout_dev": s_dev, "holdout": s_ho,
               "yearly": {str(y): {"mean": float(r["mean"]), "n": int(r["count"])}
                          for y, r in yearly.iterrows()},
               "pos_years": pos_years, "n_years": len(yearly)},
              open(f"{OUT}/s12_cross_sectional.json", "w"), indent=2)
    print(f"\n耗時 {time.perf_counter() - t0:.0f}s -> {OUT}/s12_cross_sectional.json")


if __name__ == "__main__":
    main()
