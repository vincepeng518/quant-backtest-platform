from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Optional

import pandas as pd

from app.utils.cache import cache
from data.providers.binance import BinanceProvider
from data.providers.csv_loader import CSVLoader

logger = logging.getLogger(__name__)

# In-memory task store (production → Redis)
_backtest_tasks: dict[str, dict] = {}
_optimize_tasks: dict[str, dict] = {}
_analysis_tasks: dict[str, dict] = {}


class DataService:
    def __init__(self) -> None:
        self.binance = BinanceProvider()
        self.csv_loader = CSVLoader()

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        start_date: str = "",
        end_date: str = "",
        source: str = "api",
    ) -> pd.DataFrame:
        cache_key = f"ohlcv:{symbol}:{timeframe}:{start_date}:{end_date}"
        cached = cache.get(cache_key)
        if cached is not None:
            return pd.DataFrame(cached)

        data: pd.DataFrame | None = None
        if source == "csv":
            data = self.csv_loader.load(symbol)
        else:
            try:
                data = await self.binance.fetch_ohlcv(symbol, timeframe, start_date, end_date)
            except Exception as e:  # network/geo-block etc.
                logger.warning("Binance fetch failed for %s: %s", symbol, e)
                data = None
            # Fallback to bundled CSV if live data unavailable
            if data is None or len(data) == 0:
                logger.info("Falling back to CSV for %s", symbol)
                data = self.csv_loader.load(symbol)

        if data is not None and len(data):
            cache.set(cache_key, data.to_dict(orient="records"))
        return data if data is not None else pd.DataFrame()

    async def get_symbols(self) -> list[dict]:
        # ponytail: static list for now
        return [
            {"symbol": "BTC/USDT", "market": "crypto", "exchange": "binance"},
            {"symbol": "ETH/USDT", "market": "crypto", "exchange": "binance"},
            {"symbol": "SOL/USDT", "market": "crypto", "exchange": "binance"},
        ]


def create_task_id() -> str:
    return str(uuid.uuid4())[:8]


async def _execute_backtest(task_id: str, backtester, store: dict[str, dict]) -> None:
    try:
        result = backtester.run()
        store[task_id]["status"] = "completed"
        store[task_id]["result"] = result
    except Exception as e:
        logger.exception("Backtest failed")
        store[task_id]["status"] = "error"
        store[task_id]["error"] = str(e)


def get_task(task_id: str, store: dict) -> Optional[dict]:
    return store.get(task_id)