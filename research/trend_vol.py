#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BBW / Keltner / ATR 波動收斂類指標 — 盤整 vs 趨勢判斷能力驗證
=====================================================================
標的: BTC/USDT 日線 (Binance, 2023-01 至今)
指標: Bollinger Band Width (BBW), BBW 滾動百分位, Keltner Channel 嵌套, ATR/close
信號: 3 態 (平盤 / 看多 / 看空)
回測: 每日信號 → 對照後 5 日實際走勢 → 算準確率 / 方向正確率
格點: BBW 百分位閾值 × ATR 佔比閾值 掃描找最佳

可重跑:  python research/trend_vol.py
依賴:    ccxt, pandas, pandas_ta, yfinance (fallback)
"""

import os
import sys
import json
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ----------------------------------------------------------------------------
# 0. 參數
# ----------------------------------------------------------------------------
SYMBOL = "BTC/USDT"
TIMEFRAME = "1d"
SINCE = "2023-01-01"
LOOKBACK_PCTILE = 60          # BBW 百分位滾動視窗
BB_PERIOD = 20
BB_STD = 2
KC_PERIOD = 20
KC_MULT = 1.5
ATR_PERIOD = 14
FWD = 5                       # 後 N 日對照
PCT_DEFAULT = 20              # 預設 BBW 百分位閾值
ATR_DEFAULT = 0.03            # 預設 ATR/close 閾值 (3%)

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_CACHE = os.path.join(OUT_DIR, "btc_usdt_1d.csv")


# ----------------------------------------------------------------------------
# 1. 資料抓取 (ccxt → binance, 失敗用 yfinance)
# ----------------------------------------------------------------------------
def load_data():
    if os.path.exists(DATA_CACHE):
        print(f"[data] 讀取快取 {DATA_CACHE}")
        df = pd.read_csv(DATA_CACHE, parse_dates=["timestamp"])
        return df
    df = _load_ccxt()
    if df is None:
        print("[data] ccxt 失敗, 改用 yfinance")
        df = _load_yf()
    if df is None:
        raise RuntimeError("資料抓取失敗 (ccxt + yfinance 皆失敗)")
    df.to_csv(DATA_CACHE, index=False)
    print(f"[data] 已快取 {len(df)} 根 K 線 -> {DATA_CACHE}")
    return df


def _load_ccxt():
    try:
        import ccxt
        ex = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "spot"}})
        since = ex.parse8601(SINCE + "T00:00:00Z")
        all_rows = []
        while True:
            rows = ex.fetch_ohlcv(SYMBOL, TIMEFRAME, since=since, limit=1000)
            if not rows:
                break
            all_rows += rows
            since = rows[-1][0] + 1
            if since >= ex.milliseconds():
                break
            if len(rows) < 1000:
                break
        if not all_rows:
            return None
        df = pd.DataFrame(all_rows, columns=["ts", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.tz_convert(None)
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = df[c].astype(float)
        df = df[df["timestamp"] >= pd.Timestamp(SINCE)].reset_index(drop=True)
        print(f"[data] ccxt 拉到 {len(df)} 根 (binance spot)")
        return df[["timestamp", "open", "high", "low", "close", "volume"]]
    except Exception as e:
        print(f"[data] ccxt error: {e}")
        return None


def _load_yf():
    try:
        import yfinance as yf
        tk = yf.Ticker("BTC-USD")
        raw = tk.history(start=SINCE, interval="1d", auto_adjust=False)
        if raw is None or len(raw) == 0:
            return None
        df = pd.DataFrame({
            "timestamp": raw.index.tz_localize(None),
            "open": raw["Open"].values,
            "high": raw["High"].values,
            "low": raw["Low"].values,
            "close": raw["Close"].values,
            "volume": raw["Volume"].values,
        })
        print(f"[data] yfinance 拉到 {len(df)} 根 (BTC-USD)")
        return df.reset_index(drop=True)
    except Exception as e:
        print(f"[data] yfinance error: {e}")
        return None


def _pick_kc(cols, pref):
    """KC 欄名可能為 KCUe_ (ema) 或 KCLe_sma 等, 取匹配前綴的第一個。"""
    c = [x for x in cols if x.startswith(pref)]
    return None if not c else c[0]


# ----------------------------------------------------------------------------
# 2. 指標計算
# ----------------------------------------------------------------------------
def compute_indicators(df):
    import pandas_ta as ta

    close = df["close"]
    high = df["high"]
    low = df["low"]

    # --- Bollinger Bands (20,2) ---
    bb = ta.bbands(close, length=BB_PERIOD, std=BB_STD)
    def _pick(cols, pref):
        c = [x for x in cols if x.startswith(pref)]
        return bb[c[0]]
    upper = _pick(bb.columns, "BBU_")
    mid = _pick(bb.columns, "BBM_")
    lower = _pick(bb.columns, "BBL_")
    bbw = (upper - lower) / mid          # BBW = (上帶-下帶)/中帶

    # --- BBW 滾動百分位 (60日) ---
    # 用 ranking 法: 當日 BBW 在其前 LOOKBACK_PCTILE 日中的百分位 (向量化, 穩健)
    bbw_pctile = bbw.rolling(LOOKBACK_PCTILE).apply(
        lambda x: (x[-1] <= x).mean() * 100, raw=True
    )

    # --- Keltner Channel (20, 1.5) ---
    kc = ta.kc(high, low, close, length=KC_PERIOD, scalar=KC_MULT)
    kc_upper_col = _pick_kc(kc.columns, "KCU")
    kc_lower_col = _pick_kc(kc.columns, "KCL")
    kc_upper = kc[kc_upper_col]
    kc_lower = kc[kc_lower_col]

    # --- ATR(14) / close 佔比 ---
    atr = ta.atr(high, low, close, length=ATR_PERIOD)
    atr_eff = atr / close

    out = df.copy()
    out["upper"] = upper
    out["mid"] = mid
    out["lower"] = lower
    out["bbw"] = bbw
    out["bbw_pctile"] = bbw_pctile
    out["kc_upper"] = kc_upper
    out["kc_lower"] = kc_lower
    out["atr"] = atr
    out["atr_eff"] = atr_eff
    # Keltner 嵌套: 布林帶完全包住 Keltner (收斂特徵)
    out["bb_inside_kc"] = (upper < kc_upper) & (lower > kc_lower)
    # 價格貼邊帶 (收盤在上/下帶 0.5% 內)
    tol = 0.005
    out["touch_upper"] = close >= upper * (1 - tol)
    out["touch_lower"] = close <= lower * (1 + tol)
    return out


# ----------------------------------------------------------------------------
# 3. 信號定義 (3 態)
# ----------------------------------------------------------------------------
def signal_at(row, pct_thr, atr_thr):
    """
    盤整: BBW 百分位 < pct_thr 且 ATR 佔比 < atr_thr -> flat
    趨勢 (非強盤整): BBW 擴張(百分位>50) + 貼上帶 -> long
                      BBW 擴張(百分位>50) + 貼下帶 -> short
    其餘 -> neutral
    """
    p = row["bbw_pctile"]
    a = row["atr_eff"]
    if pd.isna(p) or pd.isna(a):
        return "neutral"
    if (p < pct_thr) and (a < atr_thr):
        return "flat"
    if p > 50:
        if row["touch_upper"]:
            return "long"
        if row["touch_lower"]:
            return "short"
    return "neutral"


def signal_squeeze(row):
    """
    改良版 (Bollinger/Keltner Squeeze-Release):
    - 若當前處於 squeeze (BBands 完全包住 Keltner 且 BBW 百分位低),
      仍標記為 flat (盤整/收斂)。
    - 若前一日是 squeeze、今日收盤突破 KC 上軌 -> long (釋放向上)
      突破 KC 下軌 -> short (釋放向下)。
    - 否則 neutral。
    這才是 BBW + Keltner 組合原本的經典用法 (John Bollinger / TG).
    """
    if pd.isna(row.get("bb_inside_kc")):
        return "neutral"
    if row["bb_inside_kc"]:
        return "flat"
    # 突破判定: 收盤站上/跌破 KC 軌
    if not pd.isna(row.get("kc_upper")) and row["close"] > row["kc_upper"]:
        return "long"
    if not pd.isna(row.get("kc_lower")) and row["close"] < row["kc_lower"]:
        return "short"
    return "neutral"


# ----------------------------------------------------------------------------
# 4. 回測評估
# ----------------------------------------------------------------------------
def evaluate(df, pct_thr, atr_thr):
    sig = df.apply(lambda r: signal_at(r, pct_thr, atr_thr), axis=1)
    df = df.assign(signal=sig)

    fwd_ret = df["close"].shift(-FWD) / df["close"] - 1.0
    hi5 = df["high"].rolling(FWD).max().shift(-FWD)
    lo5 = df["low"].rolling(FWD).min().shift(-FWD)
    rng5 = (hi5 - lo5) / df["close"]

    rows = df.iloc[:-FWD].copy()
    rows["fwd_ret"] = fwd_ret.iloc[:-FWD].values
    rows["rng5"] = rng5.iloc[:-FWD].values

    flat_label = rows["signal"] == "flat"
    real_flat = rows["rng5"] <= rows["rng5"].median()
    flat_precision = (flat_label & real_flat).sum() / flat_label.sum() if flat_label.sum() > 0 else np.nan
    flat_recall = (flat_label & real_flat).sum() / real_flat.sum() if real_flat.sum() > 0 else np.nan

    trend = rows[rows["signal"].isin(["long", "short"])]
    if len(trend) > 0:
        correct = ((trend["signal"] == "long") & (trend["fwd_ret"] > 0)) | \
                  ((trend["signal"] == "short") & (trend["fwd_ret"] < 0))
        trend_acc = correct.sum() / len(trend)
    else:
        trend_acc = np.nan

    return {
        "pct_thr": pct_thr,
        "atr_thr": atr_thr,
        "n_flat": int(flat_label.sum()),
        "n_trend": int((rows["signal"].isin(["long", "short"])).sum()),
        "flat_precision": flat_precision,
        "flat_recall": flat_recall,
        "trend_acc": trend_acc,
    }


def evaluate_squeeze(df):
    """Squeeze-Release 改良版評估 (不需要閾值, squeeze 由 BB inside KC 定義)。"""
    sig = df.apply(signal_squeeze, axis=1)
    df = df.assign(signal=sig)

    fwd_ret = df["close"].shift(-FWD) / df["close"] - 1.0
    hi5 = df["high"].rolling(FWD).max().shift(-FWD)
    lo5 = df["low"].rolling(FWD).min().shift(-FWD)
    rng5 = (hi5 - lo5) / df["close"]

    rows = df.iloc[:-FWD].copy()
    rows["fwd_ret"] = fwd_ret.iloc[:-FWD].values
    rows["rng5"] = rng5.iloc[:-FWD].values

    flat_label = rows["signal"] == "flat"
    real_flat = rows["rng5"] <= rows["rng5"].median()
    flat_precision = (flat_label & real_flat).sum() / flat_label.sum() if flat_label.sum() > 0 else np.nan
    flat_recall = (flat_label & real_flat).sum() / real_flat.sum() if real_flat.sum() > 0 else np.nan

    trend = rows[rows["signal"].isin(["long", "short"])]
    if len(trend) > 0:
        correct = ((trend["signal"] == "long") & (trend["fwd_ret"] > 0)) | \
                  ((trend["signal"] == "short") & (trend["fwd_ret"] < 0))
        trend_acc = correct.sum() / len(trend)
    else:
        trend_acc = np.nan

    return {
        "n_flat": int(flat_label.sum()),
        "n_trend": int((rows["signal"].isin(["long", "short"])).sum()),
        "flat_precision": flat_precision,
        "flat_recall": flat_recall,
        "trend_acc": trend_acc,
    }


# ----------------------------------------------------------------------------
# 5. 格點搜尋
# ----------------------------------------------------------------------------
def grid_search(df):
    pct_grid = list(range(10, 41, 5))
    atr_grid = [x / 100 for x in (2, 2.5, 3, 3.5, 4, 5, 6)]
    results = []
    for p in pct_grid:
        for a in atr_grid:
            r = evaluate(df, p, a)
            fp = r["flat_precision"] if not np.isnan(r["flat_precision"]) else 0
            ta_ = r["trend_acc"] if not np.isnan(r["trend_acc"]) else 0
            score = 0.5 * fp + 0.5 * ta_ if (r["n_flat"] >= 20 and r["n_trend"] >= 20) else 0
            r["score"] = score
            results.append(r)
    return pd.DataFrame(results)


# ----------------------------------------------------------------------------
# 6. 錯判案例
# ----------------------------------------------------------------------------
def miss_cases(df, pct_thr, atr_thr):
    sig = df.apply(lambda r: signal_at(r, pct_thr, atr_thr), axis=1)
    df = df.assign(signal=sig)
    fwd_ret = df["close"].shift(-FWD) / df["close"] - 1.0
    df["fwd_ret"] = fwd_ret

    flat = df[(df["signal"] == "flat") & (df["fwd_ret"].abs() > 0.08)]
    wrong = df[((df["signal"] == "long") & (df["fwd_ret"] < -0.03)) |
               ((df["signal"] == "short") & (df["fwd_ret"] > 0.03))]

    def fmt(d):
        out = []
        for _, r in d.head(3).iterrows():
            out.append({
                "date": str(r["timestamp"].date()),
                "close": round(float(r["close"]), 0),
                "signal": r["signal"],
                "fwd_ret_pct": round(float(r["fwd_ret"]) * 100, 2),
                "bbw_pctile": round(float(r["bbw_pctile"]), 1) if pd.notna(r["bbw_pctile"]) else None,
                "atr_eff_pct": round(float(r["atr_eff"]) * 100, 2) if pd.notna(r["atr_eff"]) else None,
            })
        return out

    return {"flat_breakout": fmt(flat), "wrong_direction": fmt(wrong)}


def miss_cases_squeeze(df):
    sig = df.apply(signal_squeeze, axis=1)
    df = df.assign(signal=sig)
    fwd_ret = df["close"].shift(-FWD) / df["close"] - 1.0
    df["fwd_ret"] = fwd_ret

    flat = df[(df["signal"] == "flat") & (df["fwd_ret"].abs() > 0.08)]
    wrong = df[((df["signal"] == "long") & (df["fwd_ret"] < -0.03)) |
               ((df["signal"] == "short") & (df["fwd_ret"] > 0.03))]

    def fmt(d):
        out = []
        for _, r in d.head(3).iterrows():
            out.append({
                "date": str(r["timestamp"].date()),
                "close": round(float(r["close"]), 0),
                "signal": r["signal"],
                "fwd_ret_pct": round(float(r["fwd_ret"]) * 100, 2),
                "bb_inside_kc": bool(r["bb_inside_kc"]) if pd.notna(r["bb_inside_kc"]) else None,
                "atr_eff_pct": round(float(r["atr_eff"]) * 100, 2) if pd.notna(r["atr_eff"]) else None,
            })
        return out

    return {"flat_breakout": fmt(flat), "wrong_direction": fmt(wrong)}


# ----------------------------------------------------------------------------
# 7. 主程序
# ----------------------------------------------------------------------------
def main():
    print("=" * 70)
    print("BBW / Keltner / ATR 波動收斂指標 — 盤整判斷驗證")
    print("=" * 70)

    df = load_data()
    print(f"[data] 樣本區間: {df['timestamp'].min().date()} ~ {df['timestamp'].max().date()} ({len(df)} 根)")

    df = compute_indicators(df)
    df = df.dropna(subset=["bbw_pctile", "atr_eff"]).reset_index(drop=True)
    print(f"[ind] 有效樣本 (去掉前 {LOOKBACK_PCTILE} 根 warmup): {len(df)}")

    print("\n[stat] BBW 百分位分位數:")
    for q in [10, 25, 50, 75, 90]:
        print(f"   p{q}: {df['bbw_pctile'].quantile(q/100):.1f}")
    print("[stat] ATR/close 佔比分位數:")
    for q in [10, 25, 50, 75, 90]:
        print(f"   p{q}: {df['atr_eff'].quantile(q/100)*100:.2f}%")

    print(f"\n[base] 預設閾值 pct<{PCT_DEFAULT} & atr<{ATR_DEFAULT*100:.1f}%:")
    base = evaluate(df, PCT_DEFAULT, ATR_DEFAULT)
    for k, v in base.items():
        print(f"   {k}: {v if not isinstance(v, float) else round(v, 4)}")

    print("\n[grid] 掃描 BBW百分位 × ATR佔比 ...")
    res = grid_search(df)
    best = res.sort_values("score", ascending=False).head(1).iloc[0]
    print("\n[grid] Top 5 組合 (score = 0.5·盤整精確率 + 0.5·趨勢準確率):")
    top = res.sort_values("score", ascending=False).head(5)
    for _, r in top.iterrows():
        print(f"   pct<{int(r['pct_thr'])} atr<{r['atr_thr']*100:.1f}% | "
              f"flatP={r['flat_precision']:.3f} flatR={r['flat_recall']:.3f} "
              f"trendAcc={r['trend_acc']:.3f} nF={int(r['n_flat'])} nT={int(r['n_trend'])} "
              f"score={r['score']:.3f}")

    bp, ba = int(best["pct_thr"]), best["atr_thr"]
    print(f"\n[best] 最佳: pct<{bp} & atr<{ba*100:.1f}%")
    best_eval = evaluate(df, bp, ba)
    for k, v in best_eval.items():
        print(f"   {k}: {v if not isinstance(v, float) else round(v, 4)}")

    # --- Squeeze-Release 改良版 ---
    print("\n[squeeze] Bollinger/Keltner Squeeze-Release 改良版 (不需閾值):")
    sq = evaluate_squeeze(df)
    for k, v in sq.items():
        print(f"   {k}: {v if not isinstance(v, float) else round(v, 4)}")
    mc_sq = miss_cases_squeeze(df)

    print("\n[miss] 錯判案例 (預設閾值):")
    mc = miss_cases(df, PCT_DEFAULT, ATR_DEFAULT)
    print("  盤整卻噴 (flat 但後5日 |漲跌|>8%):")
    for c in mc["flat_breakout"]:
        print(f"    {c}")
    print("  趨勢看反 (long 跌 / short 漲 >3%):")
    for c in mc["wrong_direction"]:
        print(f"    {c}")

    # 輸出 JSON 報告
    report = {
        "sample_range": [str(df["timestamp"].min().date()), str(df["timestamp"].max().date())],
        "n_samples": len(df),
        "default": {"pct_thr": PCT_DEFAULT, "atr_thr": ATR_DEFAULT, **base},
        "best": {"pct_thr": bp, "atr_thr": ba, **best_eval},
        "top5": top.to_dict(orient="records"),
        "squeeze_release": sq,
        "miss_cases_default": mc,
        "miss_cases_squeeze": mc_sq,
    }
    report_path = os.path.join(OUT_DIR, "trend_vol_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n[out] 報告已寫入 {report_path}")


if __name__ == "__main__":
    main()
