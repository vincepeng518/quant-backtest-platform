"""橫斷面（cross-sectional）面板建構與因子檢定工具。

為什麼橫斷面能避開 Stage 10 的相關性陷阱：
  Stage 10 失敗的原因是「182 檔的留出期是同一段日曆時間、彼此相關」，
  用標的數當獨立樣本量會嚴重高估顯著性。
  橫斷面策略本身是**多空價差**（做多強的、做空弱的），相關的市場成分
  在多空兩腿互相抵消 → 訊號的獨立性來自「相對排序」，不是「絕對報酬」。
  統計檢定的獨立單位改用**時間期間**（月/季），而不是標的數。
"""
from __future__ import annotations

import glob
import os

import numpy as np
import pandas as pd

OKX_4H = "/root/okx_data"
OKX_5M = "/root/okx_data_5m"
MIN_BARS = 2500


def load_okx_4h(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df[["timestamp", "open", "high", "low", "close", "volume"]] \
             .dropna().sort_values("timestamp").reset_index(drop=True)


def load_okx_5m(usdt_tag: str) -> pd.DataFrame:
    df = pd.read_csv(f"{OKX_5M}/{usdt_tag}_USDT_5m.csv")
    df.columns = [c.lower() for c in df.columns]
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df[["timestamp", "open", "high", "low", "close", "volume"]] \
             .sort_values("timestamp").reset_index(drop=True)


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    return df.set_index("timestamp").resample(rule).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna(subset=["open", "high", "low", "close"]).reset_index()


def build_panel(tf: str = "4h", max_symbols: int | None = None,
                min_bars: int = MIN_BARS, min_universe_count: int = 20
                ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """回傳 (close_panel, high_panel/low_panel 打包的 dict)。

    panel：index=timestamp, columns=symbol，已 dropna 對齊（只保留共同時間軸）。
    """
    if tf == "4h":
        files = sorted(glob.glob(f"{OKX_4H}/*_4h.csv"))
        frames = {}
        for p in files:
            sym = os.path.basename(p)[:-7]
            try:
                df = load_okx_4h(p)
            except Exception:
                continue
            if len(df) >= min_bars:
                frames[sym] = df
    else:
        syms = [os.path.basename(x).replace("_USDT_5m.csv", "") for x in
                glob.glob(f"{OKX_5M}/*_5m.csv")]
        frames = {}
        for s in syms:
            df = resample(load_okx_5m(s), tf)
            if len(df) >= 200:
                frames[s] = df

    if max_symbols:
        # 取根數最多的前 N 檔（資料較完整）
        top = sorted(frames, key=lambda k: -len(frames[k]))[:max_symbols]
        frames = {k: frames[k] for k in top}

    closes, highs, lows, opens = {}, {}, {}, {}
    for sym, df in frames.items():
        d = df.set_index("timestamp")
        closes[sym] = d["close"]
        highs[sym] = d["high"]
        lows[sym] = d["low"]
        opens[sym] = d["open"]
    C = pd.DataFrame(closes).sort_index()
    H = pd.DataFrame(highs).sort_index()
    L = pd.DataFrame(lows).sort_index()
    O = pd.DataFrame(opens).sort_index()
    # 不要求所有標的都有資料（那會把 182 檔的交集壓成幾個月的共同區間）。
    # 只要求單一時間點有足夠檔數可供橫斷面排序 -> min_universe_count 檔。
    enough = C.notna().sum(axis=1) >= min_universe_count
    return C.loc[enough], H.loc[enough], L.loc[enough], O.loc[enough]


def drop_short_history(C: pd.DataFrame, H: pd.DataFrame, L: pd.DataFrame,
                       O: pd.DataFrame, min_obs_frac: float = 0.5):
    """移除歷史過短的標的（避免新上市標的只在尾端出現、拉高換手噪音）。"""
    keep = [c for c in C.columns if C[c].notna().mean() >= min_obs_frac]
    return C[keep], H[keep], L[keep], O[keep]


def cross_sectional_momentum_signal(
    C: pd.DataFrame, lookback: int, top_q: float = 0.2, bottom_q: float = 0.2,
    min_universe: int = 20,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """橫斷面動能：依過去 lookback 根報酬排序，回傳 (long_mask, short_mask)。

    用**確切取前 k 檔**（k = round(n_valid × q)），不用百分位邊界 ——
    百分位在小型 universe 會受邊界影響（5 檔 × 20% 可能選到 2 檔）。
    訊號只用 <= t 的資料，執行在第 t+1 根開盤（呼叫端負責）。
    """
    mom = C.pct_change(lookback, fill_method=None)
    valid = mom.notna() & (mom.notna().sum(axis=1) >= min_universe).values[:, None]
    n_valid = mom.notna().sum(axis=1)
    # 每個時間點的有效檔數（用於決定 k）
    n_eff = n_valid.where(n_valid >= min_universe, 0)

    lon = pd.DataFrame(False, index=C.index, columns=C.columns)
    sho = pd.DataFrame(False, index=C.index, columns=C.columns)
    for t in range(len(C)):
        nv = int(n_eff.iloc[t])
        if nv == 0:
            continue
        k_long = max(1, int(round(nv * top_q)))
        k_short = max(1, int(round(nv * bottom_q)))
        row = mom.iloc[t].dropna()
        if len(row) < nv:
            row = mom.iloc[t].where(valid.iloc[t]).dropna()
        if len(row) == 0:
            continue
        ordered = row.sort_values(ascending=False)
        lon.iloc[t, [C.columns.get_loc(s) for s in ordered.index[:k_long]]] = True
        sho.iloc[t, [C.columns.get_loc(s) for s in ordered.index[-k_short:]]] = True
    return lon, sho


def breakout_mask(C: pd.DataFrame, H: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """時間序列突破：收盤 > 前 lookback 根最高（不含當根）。"""
    prior_high = H.rolling(lookback).max().shift(1)
    return C > prior_high


def squeeze_mask(C: pd.DataFrame, bandwidth_pctile: float = 0.3,
                 bb_len: int = 20) -> pd.DataFrame:
    """盤整壓縮：布林帶寬位於其歷史百分位以下。"""
    ma = C.rolling(bb_len).mean()
    sd = C.rolling(bb_len).std()
    bw = (4 * sd) / ma                      # 帶寬（相對值）
    rank = bw.rolling(500, min_periods=150).rank(pct=True)
    return rank <= bandwidth_pctile
