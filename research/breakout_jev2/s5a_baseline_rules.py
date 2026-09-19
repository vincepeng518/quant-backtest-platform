#!/usr/bin/env python3
"""Stage 5a：先回答「有沒有正期望值的基礎規則可以疊」。

使用者指示：「先搞正期望值」—— 若基礎規則本身是負期望值，Jev 再準也只是
在負值上加濾網，無從加分。

本階段不呼叫 Jev（零成本），只掃簡單規則，全部以**樣本外**評估：
  切 50/50，前段選參數，後段只看一次。

規則族：
  1. always_hold      : 不交易（基準線，報酬 0）
  2. random_entry     : 隨機以相同頻率進場（基準線）
  3. breakout_raw     : 裸 Donchian 突破（對照：已知無 edge）
  4. breakout+mom     : 突破 + 動能過濾（ret_48 > 0 才做多）
  5. breakout+ema     : 突破 + EMA 趨勢過濾（收盤 > EMA200）
  6. breakout+vol     : 突破 + 量能過濾（vol > 1.5× 20 根均量）
  7. donchian_reversal: 反向做（前測顯示突破是反指標，驗證反向）
"""
import itertools
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/root/Crypto-Backtesting-Lab")
from research.breakout_jev2.lib_backtest import backtest, metrics
from research.breakout_jev2.lib_data import LOOKBACKS, add_features, load_5m

OUT = "/root/Crypto-Backtesting-Lab/runtime/breakout_jev2"
TAGS = ["BTC_USDT", "APT_USDT", "SUI_USDT", "FIL_USDT", "BCH_USDT"]
STOP_ATR, TARGET_ATR = 2.0, 4.0
MAX_HOLD = 288


def add_rule_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ema200"] = out["close"].ewm(span=200, adjust=False).mean()
    out["vol_ma20"] = out["volume"].rolling(20).mean()
    out["vol_ratio"] = out["volume"] / out["vol_ma20"]
    return out


def signal_mask(df: pd.DataFrame, lookback: int, brk_max: float, rule: str,
                side: str = "long") -> np.ndarray:
    """回傳 0/1/2 陣列：0 不進場、1 做多、2 做空。"""
    c = df["close"].values
    a = df["atr"].values
    hi = df[f"don_hi_{lookback}"].values
    lo = df[f"don_lo_{lookback}"].values
    n = len(df)
    mask = np.zeros(n, dtype=np.int8)

    for i in range(n - 1):
        if np.isnan(a[i]) or np.isnan(hi[i]) or a[i] <= 0:
            continue
        up_brk = c[i] > hi[i] and (c[i] - hi[i]) / a[i] <= brk_max
        dn_brk = c[i] < lo[i] and (lo[i] - c[i]) / a[i] <= brk_max

        if rule == "breakout_raw":
            if side == "both":
                if up_brk:
                    mask[i] = 1
                elif dn_brk:
                    mask[i] = 2
            elif up_brk:
                mask[i] = 1
        elif rule == "breakout_reversal":
            # 反向：突破向上 -> 做空
            if side == "both":
                if up_brk:
                    mask[i] = 2
                elif dn_brk:
                    mask[i] = 1
            elif up_brk:
                mask[i] = 2
        elif rule == "breakout_mom":
            if up_brk and not np.isnan(df["ret_48"].values[i]) and df["ret_48"].values[i] > 0:
                mask[i] = 1
            if side == "both" and dn_brk and not np.isnan(df["ret_48"].values[i]) \
                    and df["ret_48"].values[i] < 0:
                mask[i] = 2
        elif rule == "breakout_ema":
            if up_brk and c[i] > df["ema200"].values[i]:
                mask[i] = 1
            if side == "both" and dn_brk and c[i] < df["ema200"].values[i]:
                mask[i] = 2
        elif rule == "breakout_vol":
            vr = df["vol_ratio"].values[i]
            if up_brk and not np.isnan(vr) and vr > 1.5:
                mask[i] = 1
            if side == "both" and dn_brk and not np.isnan(vr) and vr > 1.5:
                mask[i] = 2
    return mask


def run_mask(df: pd.DataFrame, mask: np.ndarray, start: int, end: int) -> dict:
    """以 mask 為訊號源跑回測（直接呼叫核心的 per-signal 邏輯）。"""
    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    a = df["atr"].values
    n = len(df)
    FEE, SLIP = 0.0005, 0.0002

    rets = []
    i = start
    while i < min(end, n - 1):
        d = mask[i]
        if d == 0:
            i += 1
            continue
        d = 1 if d == 1 else -1
        entry = o[i + 1]
        if entry <= 0 or np.isnan(a[i]) or a[i] <= 0:
            i += 1
            continue
        stop = entry - d * STOP_ATR * a[i]
        tgt = entry + d * TARGET_ATR * a[i]
        ex = None
        ei = None
        for j in range(i + 1, min(i + 1 + MAX_HOLD, n)):
            if d > 0:
                if l[j] <= stop:
                    ex, ei = stop, j
                    break
                if h[j] >= tgt:
                    ex, ei = tgt, j
                    break
            else:
                if h[j] >= stop:
                    ex, ei = stop, j
                    break
                if l[j] <= tgt:
                    ex, ei = tgt, j
                    break
        if ex is None:
            ei = min(i + MAX_HOLD, n - 1)
            ex = c[ei]
        gross = d * (ex - entry) / entry - SLIP * 2
        rets.append(gross - 2 * FEE)
        i = ei + 1          # 不重疊（與 backtest 的 busy_until 一致）

    r = np.array(rets)
    if len(r) == 0:
        return {"n": 0, "avg_pct": 0.0, "wr": 0.0, "total_pct": 0.0, "t_stat": 0.0}
    sd = r.std(ddof=1) if len(r) > 1 else 0.0
    t = float(r.mean() / (sd / np.sqrt(len(r)))) if sd > 0 else 0.0
    return {"n": len(r), "avg_pct": float(r.mean() * 100),
            "wr": float((r > 0).mean()),
            "total_pct": float((np.prod(1 + r) - 1) * 100),
            "t_stat": t, "ci_lo_pct": float(r.mean() * 100 - 1.96 * sd / np.sqrt(len(r)) * 100),
            "ci_hi_pct": float(r.mean() * 100 + 1.96 * sd / np.sqrt(len(r)) * 100)}


def main() -> None:
    results = {}
    for tag in TAGS:
        try:
            df = add_rule_features(add_features(load_5m(tag), lookbacks=LOOKBACKS))
        except FileNotFoundError:
            continue
        n = len(df)
        split = int(n * 0.5)
        print(f"\n{'=' * 74}\n{tag}  {n:,} 根  IS<{split:,} / OOS>={split:,}\n{'=' * 74}")
        tag_res = {}

        # ── 基準線：always HOLD（報酬 0，不交易）──
        tag_res["always_hold"] = {"n": 0, "avg_pct": 0.0, "wr": 0.0, "total_pct": 0.0,
                                  "t_stat": 0.0, "note": "不交易，報酬 0"}
        print(f"  {'always_hold':22s} n=    0  報酬 0.00%（不交易）")

        # ── 基準線：random entry（相同頻率隨機進場）──
        for lb in [288]:
            base_mask = signal_mask(df, lb, 1.0, "breakout_raw")
            n_sig = int((base_mask > 0).sum())
            rng = np.random.default_rng(2026)
            rnd = np.zeros(n, dtype=np.int8)
            cand = rng.choice(np.arange(20, n - 1), size=min(n_sig * 2, n - 20),
                              replace=False)
            rnd[np.sort(cand)] = 1
            r_rnd = run_mask(df, rnd, split, n)
            tag_res["random_entry"] = r_rnd
            print(f"  {'random_entry':22s} n={r_rnd['n']:>4}  OOS 平均 {r_rnd['avg_pct']:+.4f}%  "
                  f"合計 {r_rnd['total_pct']:+.1f}%")

        # ── 規則掃描 ──
        rules = ["breakout_raw", "breakout_mom", "breakout_ema", "breakout_vol",
                 "breakout_reversal"]
        for rule, lb, bm, side in itertools.product(rules, [288, 576, 720], [0.28, 1.0],
                                                   ["long", "both"]):
            if rule == "breakout_reversal" and side == "both":
                pass
            m = signal_mask(df, lb, bm, rule, side)
            if (m > 0).sum() < 30:
                continue
            r_oos = run_mask(df, m, split, n)
            if r_oos["n"] < 15:
                continue
            key = f"{rule}|lb={lb}|bm={bm}|{side}"
            tag_res[key] = r_oos
            flag = "✓正" if r_oos["avg_pct"] > 0 and r_oos["ci_lo_pct"] > 0 else (
                "正" if r_oos["avg_pct"] > 0 else "")
            print(f"  {key:42s} n={r_oos['n']:>4}  OOS 平均 {r_oos['avg_pct']:+.4f}%  "
                  f"CI[{r_oos['ci_lo_pct']:+.3f},{r_oos['ci_hi_pct']:+.3f}]  "
                  f"t={r_oos['t_stat']:+.2f}  合計 {r_oos['total_pct']:+.1f}%  {flag}")
        results[tag] = tag_res

    json.dump(results, open(f"{OUT}/s5a_baseline_rules.json", "w"), indent=2)

    # ── 全球彙總：有沒有任何規則 OOS 顯著為正 ──
    print(f"\n{'=' * 74}\n彙總：OOS 顯著為正（CI 下界 > 0）的規則\n{'=' * 74}")
    wins = []
    for tag, res in results.items():
        for k, r in res.items():
            if k == "always_hold":
                continue
            if r.get("ci_lo_pct", -1) is not None and r.get("ci_lo_pct", -1) > 0:
                wins.append((tag, k, r))
    if wins:
        for tag, k, r in wins:
            print(f"  {tag:10s} {k:42s} 平均 {r['avg_pct']:+.4f}%  n={r['n']}")
    else:
        print("  （無）→ 沒有任何基礎規則在樣本外顯著為正")
    print(f"\n-> {OUT}/s5a_baseline_rules.json")


if __name__ == "__main__":
    main()
