from __future__ import annotations

import asyncio
import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

TF_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


class BingXProvider:
    """OHLCV provider backed by ccxt (BingX). Async wrapper around the sync client."""

    def __init__(self, symbol_default: str = "BTC/USDT") -> None:
        self._exchange = ccxt.bingx()
        self._exchange.timeout = 20_000
        self.symbol_default = symbol_default

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        start_date: str = "",
        end_date: str = "",
        limit: int = 1000,
    ) -> Optional[pd.DataFrame]:
        """Fetch OHLCV as a DataFrame with columns timestamp/open/high/low/close/volume.

        Paginates backwards from the most recent bar (or end_date) until start_date
        is reached or the exchange window limit is hit. Filters to the requested
        [start_date, end_date] window.
        """
        try:
            import ccxt

            tf_ms = TF_MS.get(timeframe, 3_600_000)
            end_ms = None
            if end_date:
                end_ms = self._exchange.parse8601(
                    f"{end_date}Z" if len(end_date) == 10 else end_date
                )
            start_ms = None
            if start_date:
                start_ms = self._exchange.parse8601(
                    f"{start_date}Z" if len(start_date) == 10 else start_date
                )

            frames: list[list] = []
            cursor = end_ms
            max_pages = 12  # cap total pull (~12k bars) to bound latency
            for _ in range(max_pages):
                raw = await asyncio.to_thread(
                    self._exchange.fetch_ohlcv,
                    symbol,
                    timeframe,
                    cursor,
                    min(limit, 1000),
                )
                if not raw:
                    break
                frames.append(raw)
                first_ts = raw[0][0]
                # stop if we've reached (or passed) the start window
                if start_ms is not None and first_ts <= start_ms:
                    break
                # move cursor earlier by one page worth of ms
                cursor = first_ts - tf_ms * min(limit, 1000)
                if cursor <= 0:
                    break

            if not frames:
                return pd.DataFrame()

            import itertools

            merged = list(itertools.chain.from_iterable(frames))
            df = pd.DataFrame(
                merged, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(float)
            df = df[["timestamp", "open", "high", "low", "close", "volume"]]
            df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")

            if start_ms is not None:
                df = df[df["timestamp"] >= pd.to_datetime(start_ms, unit="ms")]
            if end_ms is not None:
                df = df[df["timestamp"] <= pd.to_datetime(end_ms, unit="ms")]
            elif end_date:
                df = df[df["timestamp"] <= pd.to_datetime(end_date)]

            return df.reset_index(drop=True)
        except Exception as e:
            logger.warning("BingX fetch failed for %s: %s", symbol, e)
            return None
