"""
資料獲取模組
支援 CCXT（加密貨幣）與 CSV 上傳
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone
from typing import Optional, List, Dict


# 交易所專屬設定
EXCHANGE_CONFIG: Dict[str, Dict] = {
    "bingx": {
        "display_name": "BingX",
        "default_symbol": "BTC/USDT",
        "default_timeframe": "1h",
        "rate_limit_extra": 100,  # 額外延遲 ms
        "notes": "BingX 對未登入用戶有較嚴格的 rate limit，建議較長時間框架",
    },
    "binance": {
        "display_name": "Binance",
        "default_symbol": "BTC/USDT",
        "default_timeframe": "1h",
        "rate_limit_extra": 0,
    },
    "okx": {
        "display_name": "OKX",
        "default_symbol": "BTC/USDT",
        "default_timeframe": "1h",
        "rate_limit_extra": 0,
    },
    "bybit": {
        "display_name": "Bybit",
        "default_symbol": "BTC/USDT",
        "default_timeframe": "1h",
        "rate_limit_extra": 200,
    },
    "coinbasepro": {
        "display_name": "Coinbase Pro",
        "default_symbol": "BTC/USD",
        "default_timeframe": "1h",
        "rate_limit_extra": 0,
    },
    "kraken": {
        "display_name": "Kraken",
        "default_symbol": "BTC/USD",
        "default_timeframe": "1h",
        "rate_limit_extra": 0,
    },
    "bitget": {
        "display_name": "Bitget",
        "default_symbol": "BTC/USDT",
        "default_timeframe": "1h",
        "rate_limit_extra": 0,
    },
    "gate": {
        "display_name": "Gate.io",
        "default_symbol": "BTC/USDT",
        "default_timeframe": "1h",
        "rate_limit_extra": 0,
    },
    "mexc": {
        "display_name": "MEXC",
        "default_symbol": "BTC/USDT",
        "default_timeframe": "1h",
        "rate_limit_extra": 0,
    },
    "htx": {
        "display_name": "HTX (Huobi)",
        "default_symbol": "BTC/USDT",
        "default_timeframe": "1h",
        "rate_limit_extra": 0,
    },
    "kucoin": {
        "display_name": "KuCoin",
        "default_symbol": "BTC/USDT",
        "default_timeframe": "1h",
        "rate_limit_extra": 0,
    },
    "bitfinex": {
        "display_name": "Bitfinex",
        "default_symbol": "BTC/USDT",
        "default_timeframe": "1h",
        "rate_limit_extra": 0,
    },
}


def fetch_crypto_data(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    days: int = 365,
    exchange: str = "bingx",
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
    if not hasattr(ccxt, exchange):
        raise ValueError(f"CCXT 不支援 {exchange}。可用：{[e for e in ccxt.exchanges if not e.startswith('_')][:20]}")

    exchange_class = getattr(ccxt, exchange)
    config = {
        "enableRateLimit": True,
        "timeout": 30000,  # 30 秒 timeout
    }
    exchange_obj = exchange_class(config)

    # 計算起始時間
    since = int((datetime.now(timezone.utc).timestamp() - days * 86400) * 1000)

    # 抓取資料
    all_ohlcv = []
    max_iterations = 50  # 防止無限迴圈
    iteration = 0
    empty_streak = 0

    while iteration < max_iterations:
        iteration += 1
        try:
            ohlcv = exchange_obj.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        except ccxt.RateLimitExceeded as e:
            # BingX 等交易所可能會 rate limit
            import time as time_module
            wait = 5
            # 用變數讓 Python 知道 e 有被用
            _ = str(e)
            time_module.sleep(wait)
            continue
        except ccxt.ExchangeNotAvailable as e:
            raise ConnectionError(f"{exchange} 暫時無法使用：{e}")
        except ccxt.BadSymbol as e:
            raise ValueError(f"交易對 {symbol} 在 {exchange} 不存在：{e}")
        except ccxt.ExchangeError as e:
            raise RuntimeError(f"{exchange} 錯誤：{e}")

        if not ohlcv:
            empty_streak += 1
            if empty_streak >= 2:
                break
            continue

        empty_streak = 0
        all_ohlcv.extend(ohlcv)

        # 更新 since 為最後一根 K 線 + 1
        since = ohlcv[-1][0] + 1

        # 如果資料少於 1000 根，表示已抓完
        if len(ohlcv) < 1000:
            break

        # 安全機制：最多抓 50,000 根
        if len(all_ohlcv) >= 50000:
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


def get_available_exchanges() -> List[str]:
    """回傳支援的交易所清單（BingX 排第一）"""
    return list(EXCHANGE_CONFIG.keys())


def get_exchange_display_name(exchange_id: str) -> str:
    """取得交易所顯示名稱"""
    return EXCHANGE_CONFIG.get(exchange_id, {}).get("display_name", exchange_id)


def get_default_symbol(exchange_id: str) -> str:
    """取得該交易所的預設交易對"""
    return EXCHANGE_CONFIG.get(exchange_id, {}).get("default_symbol", "BTC/USDT")


def get_timeframes() -> List[str]:
    """回傳支援的時間框架"""
    return ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"]


def get_bingx_popular_symbols() -> List[str]:
    """BingX 熱門交易對"""
    return [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT",
        "BNB/USDT", "DOGE/USDT", "ADA/USDT", "AVAX/USDT",
        "LINK/USDT", "DOT/USDT", "MATIC/USDT", "TON/USDT",
        "TRX/USDT", "LTC/USDT", "SHIB/USDT", "PEPE/USDT",
    ]
