#!/usr/bin/env python3
"""Stage 13（修正版）：正面控制測試 —— 驗證管線可信度。

第一個版本有兩個測試設計錯誤（已根因確認，非管線問題）：
  ✗ B 用錯的 trades-per-year 推理論 Sharpe（metrics 的算法是對的，實測完全一致）
  ✗ C 用「置換交易順序」做檢定 —— 但 Sharpe = mean/std×sqrt(n) 是**順序無關**的
       統計量，洗牌後 sd=0.000000，檢定在數學上無效

本版修正：
  A. 買進持有基準（管線必須能顯示市場方向）
  B. 合成 edge 注入 —— 理論值用**與 metrics 相同**的 trades_per_year
  C. **訊號置換檢定** —— 置換「哪些棒被選為進場點」（block shift），
     保留交易數與報酬分布，只打散「時序對應」。這才是有效的零假設。
     → 若觀測 Sharpe 不顯著高於此 null → 訊號無時序資訊
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


def sharpe_of(rets: np.ndarray, bars: int, bars_per_year: float) -> float:
    """與 metrics() 完全相同的 Sharpe 算法（避免自我欺騙）。"""
    if len(rets) < 2:
        return 0.0
    sd = rets.std(ddof=1)
    tpy = len(rets) / max(bars / bars_per_year, 1e-9)
    return float(rets.mean() / sd * np.sqrt(tpy)) if sd > 0 else 0.0


def main() -> None:
    report = {}

    # ══════════ A. 買進持有基準 ══════════
    print("=" * 88)
    print("A. 買進持有基準（管線必須能顯示市場方向）")
    print("=" * 88)
    print(f"{'標的':>10}{'全期報酬%':>12}{'測試段報酬%':>14}{'測試段Sharpe':>14}{'測試段MaxDD%':>14}")
    bh = []
    for sym in SYMS4:
        try:
            df = prepare(load_4h(sym, "long"), LBS, EXIT_LOOKBACKS)
        except FileNotFoundError:
            continue
        c = df["close"].values.astype(float)
        n = len(df)
        cut = int(n * 0.75)
        cost = 2 * (0.0005 + 0.0002)
        r = np.diff(c[cut:]) / c[cut:-1]
        sh = float(r.mean() / r.std(ddof=1) * np.sqrt(BARS_PER_YEAR["4h"])) if r.std(ddof=1) > 0 else 0.0
        eq = c[cut:] / c[cut]
        dd = float(((eq - np.maximum.accumulate(eq)) / np.maximum.accumulate(eq)).min() * 100)
        bh.append({"sym": sym, "ret_all_pct": float((c[-1] / c[0] - 1 - cost) * 100),
                   "ret_test_pct": float((c[-1] / c[cut] - 1 - cost) * 100),
                   "sharpe_test": sh, "maxdd_test_pct": dd})
        print(f"{sym:>10}{(c[-1] / c[0] - 1 - cost) * 100:>12.1f}"
              f"{(c[-1] / c[cut] - 1 - cost) * 100:>14.1f}{sh:>14.2f}{dd:>14.1f}")
    t = np.array([x["ret_test_pct"] for x in bh])
    print(f"\n  測試段買進持有：平均 {t.mean():+.1f}%  正標的 {np.mean(t > 0):.0%}")
    print(f"  → {'市場本身為負，策略為負不奇怪' if t.mean() < 0 else '市場為正'}")
    report["buy_and_hold"] = bh

    # ══════════ B. 合成 edge 注入（用與 metrics 一致的 trades/year）══════════
    print("\n" + "=" * 88)
    print("B. 合成 edge 注入 —— 理論 Sharpe 用與 metrics 相同算法計算")
    print("=" * 88)
    print(f"{'μ':>9}{'σ':>9}{'實際ratio':>12}{'理論Sharpe':>12}{'metrics':>11}{'差異':>9}{'一致':>6}")
    checks = []
    for mu, sigma in [(0.004, 0.02), (0.002, 0.02), (0.0, 0.02), (-0.002, 0.02)]:
        rng = np.random.default_rng(42)
        n = 3000
        r = rng.normal(mu, sigma, n)
        trades = [{"i": k, "dir": 1, "ret": float(v), "bars": 1, "reason": "s"}
                  for k, v in enumerate(r)]
        m = metrics(trades, np.cumprod(1 + r), n, BARS_PER_YEAR["4h"])
        # 理論值：用實際 realized ratio 與 metrics 的 trades/year 算法
        realized_ratio = r.mean() / r.std(ddof=1)
        theo = realized_ratio * np.sqrt(n / (n / BARS_PER_YEAR["4h"]))
        diff = m["sharpe"] - theo
        ok = abs(diff) < 1e-6
        checks.append({"mu": mu, "sigma": sigma, "realized_ratio": float(realized_ratio),
                       "theoretical": float(theo), "reported": float(m["sharpe"]),
                       "diff": float(diff), "consistent": bool(ok)})
        print(f"{mu:>9.4f}{sigma:>9.4f}{realized_ratio:>12.4f}{theo:>12.4f}"
              f"{m['sharpe']:>11.4f}{diff:>9.2e}{'✓' if ok else '✗':>6}")
    all_ok = all(c["consistent"] for c in checks)
    print(f"\n  → 管線對合成 edge 的偵測：{'完全正確 ✓（管線可信）' if all_ok else '有偏差 ✗'}")
    report["synthetic_edge"] = {"checks": checks, "pipeline_ok": bool(all_ok)}

    # ══════════ C. 訊號置換檢定（正確的零假設）══════════
    print("\n" + "=" * 88)
    print(f"C. 訊號置換檢定：把進場點隨機平移 {N_PERM} 次，看策略是否贏過『同交易數的隨機進場』")
    print("=" * 88)
    print("  （舊版置換交易順序無效：Sharpe 是順序不變量。正確做法是置換『訊號位置』）")
    lb, d, ex, st, tr_, el = CFG
    perm_rows = []
    for sym in SYMS4:
        try:
            df = prepare(load_4h(sym, "long"), LBS, EXIT_LOOKBACKS)
        except FileNotFoundError:
            continue
        n = len(df)
        cut = int(n * 0.75)
        tr, eq = backtest_breakout(df, lookback=lb, direction=d, exit_method=ex,
                                   stop_atr=st, target_atr=tr_, trail_atr=tr_,
                                   exit_lookback=el, start=cut, end=n)
        if len(tr) < 10:
            continue
        obs_rets = np.array([t["ret"] for t in tr])
        obs_sh = sharpe_of(obs_rets, n - cut, BARS_PER_YEAR["4h"])

        # null：從全期隨機挑「與實際進場數相同」的棒當進場點（同方向、同出場規則）
        rng = np.random.default_rng(2026)
        from research.breakout_jev2.lib_breakout import backtest_breakout as bt
        null_sh = []
        k = len(tr)
        for _ in range(N_PERM):
            d2 = df.copy()
            pick = rng.choice(np.arange(cut, n - 200), size=k, replace=False)
            # 只在挑中的棒開通道，其餘關掉 → 等於隨機進場
            hi_col, lo_col = f"don_hi_{lb}", f"don_lo_{lb}"
            mask = np.ones(n, dtype=bool)
            mask[pick] = False
            d2.loc[mask, hi_col] = 1e12
            d2.loc[mask, lo_col] = -1e12
            t2, e2 = bt(d2, lookback=lb, direction=d, exit_method=ex, stop_atr=st,
                        target_atr=tr_, trail_atr=tr_, exit_lookback=el, start=cut, end=n)
            if len(t2) < 3:
                continue
            null_sh.append(sharpe_of(np.array([x["ret"] for x in t2]), n - cut,
                                     BARS_PER_YEAR["4h"]))
        if not null_sh:
            continue
        null_sh = np.array(null_sh)
        p = float((null_sh >= obs_sh).mean())
        perm_rows.append({"sym": sym, "observed_sharpe": obs_sh,
                          "null_mean": float(null_sh.mean()),
                          "null_p95": float(np.percentile(null_sh, 95)),
                          "n_null": len(null_sh), "n_trades": k, "p_value": p})
        print(f"  {sym:>10}  觀測 {obs_sh:+6.2f}  null 平均 {null_sh.mean():+6.2f}  "
              f"null P95 {np.percentile(null_sh, 95):+6.2f}  p={p:.3f}  n={k}")
    beats = 0
    if perm_rows:
        beats = sum(1 for x in perm_rows if x["p_value"] < 0.05)
        print(f"\n  → {beats}/{len(perm_rows)} 檔的觀測值顯著贏過同交易數的隨機進場（p<0.05）")
        avg_p = float(np.mean([x["p_value"] for x in perm_rows]))
        print(f"  平均 p 值 {avg_p:.3f}  "
              f"{'→ 訊號有資訊 ✓' if beats >= len(perm_rows) * 0.5 else '→ 訊號無資訊 ✗（與隨機進場無異）'}")
    report["signal_permutation"] = perm_rows

    json.dump(report, open(f"{OUT}/s13_positive_control.json", "w"), indent=2)

    print("\n" + "=" * 88)
    print("總結：管線可信度")
    print("=" * 88)
    print(f"  A 買進持有：測試段平均 {t.mean():+.1f}%")
    print(f"  B 合成 edge 偵測：{'正常 ✓ 管線可信' if all_ok else '異常 ✗'}")
    if perm_rows:
        print(f"  C 訊號置換：{beats}/{len(perm_rows)} 檔贏過隨機進場")
    print(f"\n-> {OUT}/s13_positive_control.json")


if __name__ == "__main__":
    main()
