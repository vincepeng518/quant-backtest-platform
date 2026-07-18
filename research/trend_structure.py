#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
趨勢結構類指標驗證 (Donchian + 樞軸通道 + SMA 排列)
========================================================
目標：用真實 BTC/USDT 日線驗證「價格結構類指標」判斷
      盤整 (flat) vs 突破趨勢 (long/short) 的能力，輸出 3 態信號。

指標：
  1. Donchian Channel(period) 高低軌
  2. 價格在 [lower, upper] 區間內連續停留天數 (range days)
  3. 樞軸通道 HL2 ± k*ATR(period)
  4. SMA(50) vs SMA(200) 多空排列

信號定義：
  - long  : 收盤突破 Donchian 上軌 且 SMA50 > SMA200
  - short : 收盤跌破 Donchian 下軌 且 SMA50 < SMA200
  - flat  : 價格在 Donchian 區間內連續停留 >= N 日 且 SMA 糾結(|SMA50-SMA200|/SMA200 < tol)

回測：
  - 在信號日 t 標記，對照 t+5 日收盤實際走勢
  - flat 準確率 = (t+5 收盤仍在區間內 或 波動 < threshold) / flat 信號數
  - 趨勢方向正確率 = (long 且 5日後漲 / short 且 5日後跌) / 趨勢信號數

格點搜索：N ∈ {5,8,12,16,20,25}, Donchian period ∈ {10,15,20,25,30}

可重跑： python research/trend_structure.py
"""

import os
import sys
import datetime as dt
import numpy as np
import pandas as pd

try:
    import ccxt
except ImportError:
    ccxt = None

try:
    import yfinance as yf
except ImportError:
    yf = None

# ----------------------------------------------------------------------------
# 1. 數據獲取
# ----------------------------------------------------------------------------
SYMBOL = "BTC/USDT"
TIMEFRAME = "1d"
START = "2023-01-01"
END = dt.date.today().isoformat()

CACHE_PATH = os.path.join(os.path.dirname(__file__), "btc_usdt_daily.csv")


def fetch_ohlcv_ccxt(symbol=SYMBOL, timeframe=TIMEFRAME, start=START, end=END):
    if ccxt is None:
        raise RuntimeError("ccxt 未安裝")
    ex = ccxt.binance()
    since = ex.parse8601(pd.Timestamp(start).strftime("%Y-%m-%dT00:00:00Z"))
    end_ms = ex.parse8601(pd.Timestamp(end).strftime("%Y-%m-%dT00:00:00Z"))
    all_rows = []
    while since < end_ms:
        rows = ex.fetch_ohlcv(symbol, timeframe, since, limit=1000)
        if not rows:
            break
        all_rows.extend(rows)
        since = rows[-1][0] + 1
        if len(rows) < 1000:
            break
    df = pd.DataFrame(all_rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["date"] = pd.to_datetime(df["ts"], unit="ms")
    return df.set_index("date").sort_index()


def fetch_ohlcv_yf(start=START, end=END):
    if yf is None:
        raise RuntimeError("yfinance 未安裝")
    df = yf.download("BTC-USD", start=start, end=end, interval="1d", auto_adjust=False)
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = ["open", "high", "low", "close", "volume"]
    return df.sort_index()


def load_data():
    if os.path.exists(CACHE_PATH):
        print(f"[data] 使用快取 {CACHE_PATH}")
        return pd.read_csv(CACHE_PATH, index_col=0, parse_dates=True)
    print("[data] 嘗試 ccxt/binance ...")
    try:
        df = fetch_ohlcv_ccxt()
        print(f"[data] ccxt OK {len(df)} 行")
    except Exception as e:
        print(f"[data] ccxt 失敗: {e}，改用 yfinance ...")
        df = fetch_ohlcv_yf()
        print(f"[data] yfinance OK {len(df)} 行")
    df.to_csv(CACHE_PATH)
    return df


# ----------------------------------------------------------------------------
# 2. 指標計算
# ----------------------------------------------------------------------------
def donchian(df, period):
    """返回 upper / lower 軌 (不含當根，標準 Donchian)。"""
    upper = df["high"].rolling(period).max().shift(1)
    lower = df["low"].rolling(period).min().shift(1)
    return upper, lower


def atr(df, period):
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def pivot_channel(df, period=20, k=1.5):
    """樞軸通道: HL2 ± k * ATR(period)。返回 mid/pupper/plower。"""
    hl2 = (df["high"] + df["low"]) / 2.0
    a = atr(df, period)
    return hl2 + k * a, hl2 - k * a, hl2


def sma(df, n):
    return df["close"].rolling(n).mean()


def compute_indicators(df, dc_period, pivot_period=20, pivot_k=1.5):
    up, lo = donchian(df, dc_period)
    pu, pl, mid = pivot_channel(df, pivot_period, pivot_k)
    s50 = sma(df, 50)
    s200 = sma(df, 200)
    out = df[["open", "high", "low", "close", "volume"]].copy()
    out["dc_up"] = up
    out["dc_lo"] = lo
    out["pivot_up"] = pu
    out["pivot_lo"] = pl
    out["sma50"] = s50
    out["sma200"] = s200
    return out


# ----------------------------------------------------------------------------
# 3. 信號定義
# ----------------------------------------------------------------------------
def range_stay_days(close, dc_up, dc_lo):
    """計算截至當日，價格連續停留在 [dc_lo, dc_up] 區間內的天數。"""
    inside = (close >= dc_lo) & (close <= dc_up)
    # 向後累計連續 inside 的長度
    groups = (~inside).cumsum()
    counts = inside.groupby(groups).cumsum()
    # 對 inside=False 的設為 0
    counts = counts.where(inside, 0)
    return counts


def generate_signal(df, N, sma_tol=0.02):
    """3 態信號: long / short / flat / none。"""
    close = df["close"]
    dc_up, dc_lo = df["dc_up"], df["dc_lo"]
    s50, s200 = df["sma50"], df["sma200"]
    stay = range_stay_days(close, dc_up, dc_lo)

    sig = pd.Series(index=df.index, dtype=object)
    sig[:] = "none"

    # 突破上軌
    long_cond = (close > dc_up) & (s50 > s200)
    # 跌破下軌
    short_cond = (close < dc_lo) & (s50 < s200)
    # 盤整: 區間內停留 >= N 且 SMA 糾結
    flat_cond = (stay >= N) & (s200.notna()) & \
                ((s50 - s200).abs() / s200 < sma_tol)

    sig[long_cond] = "long"
    sig[short_cond] = "short"
    sig[flat_cond] = "flat"
    # 優先級: flat 只在非突破時成立 (突破日歸趨勢)
    sig[(flat_cond) & (long_cond | short_cond)] = \
        sig[(flat_cond) & (long_cond | short_cond)]
    return sig, stay


# ----------------------------------------------------------------------------
# 4. 回測
# ----------------------------------------------------------------------------
def backtest(df, signal, fwd=5):
    """對照 t 日信號與 t+fwd 日收盤走勢。"""
    close = df["close"]
    dc_up, dc_lo = df["dc_up"], df["dc_lo"]
    fwd_close = close.shift(-fwd)

    rows = []
    for i in range(len(df)):
        s = signal.iloc[i]
        if s in ("none",):
            continue
        t = df.index[i]
        if i + fwd >= len(df):
            break
        c0 = close.iloc[i]
        cf = fwd_close.iloc[i]
        ret = (cf - c0) / c0
        # flat 判定: 5日後收盤仍在當日 Donchian 區間附近 & 波動小
        still_in = (cf >= dc_lo.iloc[i]) and (cf <= dc_up.iloc[i])
        vol_ok = abs(ret) < 0.03
        rows.append({
            "date": t, "signal": s, "close0": c0, "close5": cf,
            "ret5": ret, "in_range5": still_in, "vol_ok": vol_ok,
        })
    return pd.DataFrame(rows)


def evaluate(bt, signal_series):
    """計算 flat 準確率 與 趨勢方向正確率，並抽取錯判案例。"""
    if bt.empty:
        return {}, pd.DataFrame(), pd.DataFrame()

    flat = bt[bt["signal"] == "flat"]
    trend = bt[bt["signal"].isin(["long", "short"])]

    flat_acc = 0.0
    if len(flat):
        # 盤整預期 5日內不大動: 收盤仍在區間內 或 波動<3%
        flat_acc = (flat["in_range5"] | flat["vol_ok"]).mean()

    trend_acc = 0.0
    trend_correct = pd.Series(dtype=bool)
    if len(trend):
        correct = ((trend["signal"] == "long") & (trend["ret5"] > 0)) | \
                  ((trend["signal"] == "short") & (trend["ret5"] < 0))
        trend_acc = correct.mean()
        trend_correct = correct

    # wrong cases
    wrong_trend = trend[trend_correct == False] if len(trend) else pd.DataFrame()
    wrong_flat = flat[(~(flat["in_range5"] | flat["vol_ok"]))] if len(flat) else pd.DataFrame()

    metrics = {
        "n_flat": len(flat),
        "flat_acc": flat_acc,
        "n_trend": len(trend),
        "trend_acc": trend_acc,
        "n_total": len(bt),
    }
    return metrics, wrong_trend, wrong_flat


# ----------------------------------------------------------------------------
# 5. 格點搜索
# ----------------------------------------------------------------------------
def grid_search(df, N_list, dc_list, fwd=5):
    results = []
    for dc in dc_list:
        ind = compute_indicators(df, dc)
        for N in N_list:
            sig, stay = generate_signal(ind, N)
            bt = backtest(ind, sig, fwd)
            m, _, _ = evaluate(bt, sig)
            results.append({
                "dc_period": dc, "N": N,
                "n_flat": m["n_flat"], "flat_acc": m["flat_acc"],
                "n_trend": m["n_trend"], "trend_acc": m["trend_acc"],
                "n_total": m["n_total"],
                # 綜合得分: 兩項準確率平均，給足樣本加權
                "score": (m["flat_acc"] * min(m["n_flat"], 50) / 50 +
                          m["trend_acc"] * min(m["n_trend"], 50) / 50) / 2,
            })
    res = pd.DataFrame(results)
    return res


# ----------------------------------------------------------------------------
# 6. 主流程
# ----------------------------------------------------------------------------
def main():
    df = load_data()
    print(f"[info] 數據區間 {df.index.min().date()} ~ {df.index.max().date()} "
          f"共 {len(df)} 根日線")

    N_list = [5, 8, 12, 16, 20, 25]
    dc_list = [10, 15, 20, 25, 30]

    print("\n=== 格點搜索 (N × Donchian period) ===")
    grid = grid_search(df, N_list, dc_list)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    print(grid.sort_values("score", ascending=False).to_string(index=False))

    best = grid.sort_values("score", ascending=False).iloc[0]
    best_N, best_dc = int(best["N"]), int(best["dc_period"])
    print(f"\n[best] N={best_N}, Donchian={best_dc}  "
          f"flat_acc={best['flat_acc']:.3f} trend_acc={best['trend_acc']:.3f}")

    # 用最佳參數做完整回測與錯判案例
    ind = compute_indicators(df, best_dc)
    sig, stay = generate_signal(ind, best_N)
    bt = backtest(ind, sig, 5)
    m, wrong_trend, wrong_flat = evaluate(bt, sig)

    print("\n=== 最佳參數回測結果 ===")
    print(f"總信號數: {m['n_total']}  (flat={m['n_flat']}, trend={m['n_trend']})")
    print(f"盤整識別準確率: {m['flat_acc']:.3f}")
    print(f"趨勢方向正確率: {m['trend_acc']:.3f}")

    print("\n=== 錯判案例 (趨勢方向反了) ===")
    if len(wrong_trend):
        cols = ["date", "signal", "close0", "close5", "ret5"]
        print(wrong_trend[cols].head(8).to_string(index=False))
    else:
        print("(無)")

    print("\n=== 錯判案例 (盤整其實大動) ===")
    if len(wrong_flat):
        cols = ["date", "close0", "close5", "ret5"]
        print(wrong_flat[cols].head(8).to_string(index=False))
    else:
        print("(無)")

    # 信號分佈
    print("\n=== 信號分佈 ===")
    print(sig.value_counts().to_string())

    # 儲存結果
    out_dir = os.path.dirname(__file__)
    grid.to_csv(os.path.join(out_dir, "trend_grid.csv"), index=False)
    bt.to_csv(os.path.join(out_dir, "trend_backtest.csv"), index=False)
    print(f"\n[output] 格點 -> {os.path.join(out_dir, 'trend_grid.csv')}")
    print(f"[output] 回測 -> {os.path.join(out_dir, 'trend_backtest.csv')}")


if __name__ == "__main__":
    main()
