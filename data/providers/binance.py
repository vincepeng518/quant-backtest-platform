from __future__ import annotations

import logging
from typing import Optional

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

BINANCE_REST = "https://api.binance.com/api/v3"


class BinanceProvider:
    """Async OHLCV provider for Binance spot markets."""

    def __init__(self, base_url: str = BINANCE_REST) -> None:
        self.base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        start_date: str = "",
        end_date: str = "",
        limit: int = 1000,
    ) -> Optional[pd.DataFrame]:
        """Fetch OHLCV as a DataFrame with columns timestamp/open/high/low/close/volume."""
        client = await self._get_client()
        params = {
            "symbol": symbol.replace("/", ""),
            "interval": timeframe,
            "limit": limit,
        }
        try:
            resp = await client.get(f"{self.base_url}/klines", params=params)
            resp.raise_for_status()
            raw = resp.json()
        except Exception as e:
            logger.warning("Binance fetch failed for %s: %s", symbol, e)
            return None

        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(
            raw,
            columns=[
                "timestamp", "open", "high", "low", "close", "volume",
                "close_time", "quote_volume", "trades", "taker_buy_base",
                "taker_buy_quote", "ignore",
            ],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        return df[["timestamp", "open", "high", "low", "close", "volume"]]

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
