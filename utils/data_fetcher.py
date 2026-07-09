"""
資料獲取模組
支援 CCXT（加密貨幣）與 CSV 上傳
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone
from typing import Optional


def fetch_crypto_data(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    days: int = 365,
    exchange: str = "binance",
) -> Optional[pd.DataFrame]:
    """
    從交易所抓取加密貨幣歷史 K 線
    symbol: 交易對，如 BTC/USDT
    timeframe: 1m, 5m, 15m, 1h, 4h, 1d, 1w
    days: 回看天數
    exchange: 交易所名稱
    """
    try:
        import ccxt
    except ImportError:
        raise ImportError("請先安裝 ccxt: pip install ccxt")

    # 建立交易所物件
    exchange_class = getattr(ccxt, exchange)
    exchange_obj = exchange_class({"enableRateLimit": True})

    # 計算起始時間
    since = int((datetime.now(timezone.utc).timestamp() - days * 86400) * 1000)

    # 抓取資料
    all_ohlcv = []
    while True:
        ohlcv = exchange_obj.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        if not ohlcv:
            break
        all_ohlcv.extend(ohlcv)
        # 更新 since 為最後一根 K 線 + 1
        since = ohlcv[-1][0] + 1
        # 如果資料少於 1000 根，表示已抓完
        if len(ohlcv) < 1000:
            break
        # 安全機制：最多抓 200 批次
        if len(all_ohlcv) >= 200 * 1000:
            break

    if not all_ohlcv:
        return None

    # 轉成 DataFrame
    df = pd.DataFrame(all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df.set_index("timestamp", inplace=True)
    df = df[~df.index.duplicated(keep="first")].sort_index()

    return df


def load_csv_data(file) -> Optional[pd.DataFrame]:
    """
    載入使用者上傳的 CSV 檔案
    自動偵測常見欄位命名
    """
    try:
        df = pd.read_csv(file)
    except Exception as e:
        raise ValueError(f"CSV 讀取失敗: {e}")

    # 嘗試找時間欄位
    time_col_candidates = ["timestamp", "datetime", "date", "time", "Date", "Time", "Datetime"]
    time_col = None
    for col in time_col_candidates:
        if col in df.columns:
            time_col = col
            break

    if time_col is None:
        # 假設第一欄是時間
        time_col = df.columns[0]
        try:
            pd.to_datetime(df[time_col])
        except Exception:
            raise ValueError("找不到時間欄位。請確認 CSV 有 'timestamp' / 'datetime' / 'date' 等欄位")

    df[time_col] = pd.to_datetime(df[time_col])
    df.set_index(time_col, inplace=True)

    # 標準化欄位名稱
    col_map = {
        "Open": "open", "open": "open", "o": "open",
        "High": "high", "high": "high", "h": "high",
        "Low": "low", "low": "low", "l": "low",
        "Close": "close", "close": "close", "c": "close",
        "Volume": "volume", "volume": "volume", "v": "volume", "vol": "volume",
    }
    df.rename(columns=col_map, inplace=True)

    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"CSV 缺少必要欄位: {missing}。至少需要 OHLC 四個欄位")

    # 確保數值型別
    for col in required:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")

    df.dropna(inplace=True)
    df.sort_index(inplace=True)

    return df


def get_available_exchanges() -> list:
    """回傳支援的交易所清單（CCXT 內建的熱門選項）"""
    return [
        "binance", "okx", "bybit", "coinbasepro", "kraken",
        "bitget", "gate", "mexc", "htx", "kucoin", "bitfinex",
    ]


def get_timeframes() -> list:
    """回傳支援的時間框架"""
    return ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"]
