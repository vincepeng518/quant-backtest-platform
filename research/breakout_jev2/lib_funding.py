"""資金費率資料載入（Binance USDT-M 永續）。

資料源：/root/funding_arb/data_binance/*.json，格式 {"symbol","n","rates":[...]}
時間軸：8h 一次（00:00 / 08:00 / 16:00 UTC），3295 筆 ≈ 3.01 年（2023-08 ~ 2026-08）。

已驗證對齊（2026-09-20）：以 Binance API fapi/v1/fundingRate 抓 2023-11-15 起
1000 筆，比對舊存檔 rates[319:339] 完全一致（atol=1e-9）
  → rates[0] ≈ 2023-08-01。

⚠️ 限制：價格資料來自 Bybit（bxdata），資金費率來自 Binance。
   不同交易所的資金費率高度相關，但非完全等價 —— 當作代理變數使用，
   結論須標明此假設。
"""
from __future__ import annotations

import glob
import json
import os

import numpy as np
import pandas as pd

FUNDING_DIR = "/root/funding_arb/data_binance"

# 已驗證的起始時間（UTC）：rates[0] = 2023-08-01 00:00
EPOCH = pd.Timestamp("2023-08-01 00:00:00", tz=None)
INTERVAL_H = 8


def load_funding(symbol: str) -> pd.Series:
    """回傳 index=UTC 時間戳、值=資金費率（每 8h）的 Series。

    symbol 例：'BTCUSDT'。找不到檔案時拋 FileNotFoundError。
    """
    path = os.path.join(FUNDING_DIR, f"{symbol}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with open(path) as fh:
        obj = json.load(fh)
    rates = np.asarray(obj["rates"], dtype=float)
    idx = pd.DatetimeIndex(
        [EPOCH + pd.Timedelta(hours=INTERVAL_H * i) for i in range(len(rates))]
    )
    return pd.Series(rates, index=idx, name=symbol)


def available_funding() -> list[str]:
    """可用資金費率的標的（排除 _summary）。"""
    fs = glob.glob(f"{FUNDING_DIR}/*.json")
    return sorted(os.path.basename(p)[:-5] for p in fs
                  if not os.path.basename(p).startswith("_"))


def align_to_bars(fund: pd.Series, idx: pd.DatetimeIndex,
                  max_stale_h: int = 8) -> pd.Series:
    """把 8h 資金費率 as-of 對齊到 K 線時間軸。

    使用「最後一個已知值」（forward fill），但超過 max_stale_h 小時沒有更新
    則視為 NaN（避免用過期資料）。刻意不用 bfill —— 那會引入未來資訊。
    """
    f = fund.sort_index()
    pos = f.index.searchsorted(idx, side="right") - 1
    out = np.full(len(idx), np.nan)
    ok = pos >= 0
    if ok.any():
        vals = f.values[pos[ok]]
        age_h = (idx[ok].values - f.index.values[pos[ok]]) / np.timedelta64(1, "h")
        fresh = age_h <= max_stale_h
        tmp = np.full(ok.sum(), np.nan)
        tmp[fresh] = vals[fresh]
        out[ok] = tmp
    return pd.Series(out, index=idx)
