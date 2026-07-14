from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

# Yahoo Finance chart API (免依赖, 不用 yfinance 包)
_YF_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

# yfinance interval -> Yahoo range/period 近似
# 1m 仅近 7 天数据, 这里统一用较长周期
_TF_MAP = {
    "1m": ("1d", "5m"),
    "5m": ("1mo", "5m"),
    "15m": ("3mo", "15m"),
    "30m": ("6mo", "30m"),
    "1h": ("1y", "1h"),
    "4h": ("2y", "1h"),
    "1d": ("5y", "1d"),
}


class TradFiProvider:
    """TradFi OHLCV via Yahoo Finance public chart API (httpx, no yfinance dep).

    覆盖股票/ETF/指数/外汇/商品。symbol 用 Yahoo ticker，例如：
      AAPL, TSLA, NVDA, SPY, QQQ, EURUSD=X, GC=F (黄金), CL=F (原油)
    返回与 BingXProvider 同构的 DataFrame[timestamp,open,high,low,close,volume]。
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
            rng, interval = _TF_MAP.get(timeframe, ("5y", "1d"))
            params = {"range": rng, "interval": interval}
            headers = {"User-Agent": "Mozilla/5.0 (compatible; backtest-bot/1.0)"}

            async with httpx.AsyncClient(timeout=40.0, headers=headers, follow_redirects=True) as client:
                resp = await client.get(_YF_URL.format(symbol=symbol), params=params)
                resp.raise_for_status()
                data = resp.json()

            res = data.get("chart", {}).get("result")
            if not res:
                logger.warning("Yahoo chart empty for %s", symbol)
                return None
            meta = res[0].get("meta", {})
            ts = res[0].get("timestamp")
            q = res[0].get("indicators", {}).get("quote", [{}])[0]
            if not ts or not q.get("close"):
                return None

            df = pd.DataFrame({
                "timestamp": pd.to_datetime(pd.Series(ts), unit="s"),
                "open": pd.Series(q.get("open", [])).astype(float),
                "high": pd.Series(q.get("high", [])).astype(float),
                "low": pd.Series(q.get("low", [])).astype(float),
                "close": pd.Series(q.get("close", [])).astype(float),
                "volume": pd.Series(q.get("volume", [])).fillna(0).astype(float),
            })
            df = df.dropna(subset=["close"]).reset_index(drop=True)

            # 按 start/end 过滤
            if start_date:
                df = df[df["timestamp"] >= pd.Timestamp(start_date)]
            if end_date:
                df = df[df["timestamp"] <= pd.Timestamp(end_date)]

            df = df[["timestamp", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
            return df if len(df) else None
        except Exception as e:
            logger.warning("TradFi (Yahoo) fetch failed for %s: %s", symbol, e)
            return None
