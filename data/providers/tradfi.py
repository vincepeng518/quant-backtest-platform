from __future__ import annotations

import asyncio
import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# yfinance interval 支持；1m 仅近 7 天，故短周期统一映射到 5m/60m
_TF_MAP = {
    "1m": "5m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "60m",
    "4h": "1h",
    "1d": "1d",
}


class TradFiProvider:
    """TradFi OHLCV via yfinance (Yahoo Finance).

    覆盖股票/ETF/指数/外汇/商品。symbol 用 Yahoo ticker，例如：
      AAPL, TSLA, NVDA, SPY, QQQ, EURUSD=X, GC=F (黄金), CL=F (原油)
    返回与 BingXProvider 同构的 DataFrame。
    """

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1d",
        start_date: str = "",
        end_date: str = "",
        limit: int = 1000,
    ) -> Optional[pd.DataFrame]:
        try:
            import yfinance as yf

            interval = _TF_MAP.get(timeframe, "1d")
            kwargs: dict = {"interval": interval, "auto_adjust": True, "repair": False}
            if start_date:
                kwargs["start"] = start_date
            if end_date:
                kwargs["end"] = end_date

            def _download() -> pd.DataFrame:
                return yf.download(
                    symbol, progress=False, actions=False, **kwargs
                )

            df = await asyncio.to_thread(_download)
            if df is None or len(df) == 0:
                logger.warning("yfinance returned empty for %s", symbol)
                return None

            # yfinance 多列为 MultiIndex (Close, ...) — 压平
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] for c in df.columns]

            df = df.reset_index()
            out = pd.DataFrame()
            out["timestamp"] = pd.to_datetime(df["Date"] if "Date" in df else df.iloc[:, 0])
            out["open"] = df["Open"].astype(float).values
            out["high"] = df["High"].astype(float).values
            out["low"] = df["Low"].astype(float).values
            out["close"] = df["Close"].astype(float).values
            # 成交量可能为 NaN（指数/外汇有时缺）
            vol = df.get("Volume")
            if vol is None:
                out["volume"] = 0.0
            else:
                out["volume"] = vol.fillna(0).astype(float).values
            out = out[["timestamp", "open", "high", "low", "close", "volume"]]
            out = out.dropna(subset=["close"]).reset_index(drop=True)
            return out if len(out) else None
        except Exception as e:
            logger.warning("TradFi (yfinance) fetch failed for %s: %s", symbol, e)
            return None
