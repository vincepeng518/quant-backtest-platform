#!/usr/bin/env python3
"""Stage 3：蒙地卡羅（含槓桿路徑、爆倉、破產、月報酬分布）。

與 engine/analyzer.MonteCarloSimulator 的差異（必須自行實作的理由）：
  - 它把每一根 bar 當一天 -> 5m 資料上嚴重失真
  - 它沒有破產/槓桿/爆倉概念
本腳本：
  1. 以**每筆交易報酬**重抽樣
  2. 多種槓桿並排
  3. 直接換算「達到月化 20% 的機率」
  4. 回撤門檻：加槓桿後 maxdd P95 必須 <= 30%，否則該槓桿淘汰（用戶指定上限）

槓桿採**事後線性套用**（ret*L + 爆倉歸零），不含追繳減倉的動態路徑 -> 報告須標註。
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, "/root/Crypto-Backtesting-Lab")
from research.breakout_jev2.lib_backtest import backtest, metrics
from research.breakout_jev2.lib_data import LOOKBACKS, add_features, load_5m
from research.breakout_jev2.lib_stats import mc_paths, mc_summary, required_samples

OUT = "/root/Crypto-Backtesting-Lab/runtime/breakout_jev2"
N_SIMS = 10_000
N_TRADES_PER_SIM = 600
LEVERAGES = [1, 3, 5, 10]
MAX_DD_PCT = 30.0
MAX_RUIN_PCT = 5.0
TAGS = ["BTC_USDT", "APT_USDT", "SUI_USDT", "FIL_USDT", "BCH_USDT"]


def best_lookback(tag: str, default: int = 576) -> int:
    """從 s1_edge.json 挑零費平均最高的 lookback（沒有就回 default）。"""
    p = f"{OUT}/s1_edge.json"
    if not os.path.exists(p):
        return default
    d = json.load(open(p))
    rows = d.get(tag, [])
    return max(rows, key=lambda r: r["zero_fee_avg_pct"])["lookback"] if rows else default


def simulate_leverage(rets: np.ndarray, leverage: float) -> np.ndarray:
    """線性套用槓桿 + 爆倉（單筆虧損 >= 1/L - 維持保證金 視為歸零）。"""
    r = rets * leverage
    liq = r <= -(1.0 - 0.005)
    return np.where(liq, -1.0, r)


def main() -> None:
    payload = {}
    for tag in TAGS:
        try:
            df = add_features(load_5m(tag), lookbacks=LOOKBACKS)
        except FileNotFoundError:
            continue
        lb = best_lookback(tag)
        tr, eq = backtest(df, lb, 2.0, 4.0, 1.0)
        base = np.array([t["ret"] for t in tr])
        if len(base) < 30:
            print(f"[skip] {tag} 樣本不足 {len(base)}")
            continue
        m = metrics(tr, eq, len(df))
        print(f"\n{'=' * 70}\n{tag}  lookback={lb}  基礎：n={m['n']}  "
              f"每筆平均 {m['avg_pct']:+.4f}%  {m['trades_per_day']:.2f} 筆/日  "
              f"期間 {m['months']:.1f} 個月\n{'=' * 70}")
        rows = {}
        for L in LEVERAGES:
            r = simulate_leverage(base, L)
            paths = mc_paths(r, n_steps=N_TRADES_PER_SIM, n_sims=N_SIMS, seed=7)
            s = mc_summary(paths)
            months = N_TRADES_PER_SIM / max(m["trades_per_day"] * 30, 1e-9)
            monthly = (s["median"] ** (1.0 / max(months, 1e-9)) - 1) * 100
            p20 = float((paths[:, -1] >= 1.20 ** months).mean() * 100)
            feasible = (s["maxdd_p95_pct"] < MAX_DD_PCT and
                        s["bankruptcy_prob_pct"] <= MAX_RUIN_PCT)
            rows[f"{L}x"] = {**s, "months_horizon": months,
                             "median_monthly_pct": monthly,
                             "prob_hit_20pct_monthly": p20,
                             "feasible_within_30dd": bool(feasible),
                             "maxdd_p95_feasible": bool(s["maxdd_p95_pct"] < MAX_DD_PCT)}
            print(f"  {L:>2}x: 中位最終 {s['median']:.3f}  P5 {s['p5']:.3f}  "
                  f"破產 {s['bankruptcy_prob_pct']:.1f}%  中位月化 {monthly:+.2f}%  "
                  f"MaxDD P95 {s['maxdd_p95_pct']:.1f}%  達月化20%機率 {p20:.1f}%  "
                  f"{'可用' if feasible else '淘汰'}")
        need = required_samples(m["trades_per_day"] * 30, 0.20, 1.5, 0.0014, m["wr"])
        payload[tag] = {"lookback": lb, "base": m, "leverage": rows,
                        "required_trades_for_20pct": need}
        print(f"  → 達月化 20% 所需樣本（保守估計）: {need:,.0f} 筆交易 vs 實測 {m['n']} 筆")
    json.dump(payload, open(f"{OUT}/s3_monte_carlo.json", "w"), indent=2)
    print(f"\n-> {OUT}/s3_monte_carlo.json")


if __name__ == "__main__":
    main()
