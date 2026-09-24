from __future__ import annotations

import logging
from typing import Optional

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

BINANCE_REST = "https://api.binance.com/api/v3"

TF_MS = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "6h": 21_600_000,
    "8h": 28_800_000, "12h": 43_200_000, "1d": 86_400_000, "3d": 259_200_000,
    "1w": 604_800_000,
}

# Page cap (1000 bars/page): 1m for ~1 year ≈ 526 pages.
MAX_PAGES = 600


def _to_ms(date: str) -> int:
    ts = pd.Timestamp(date)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return int(ts.timestamp() * 1000)


class BinanceProvider:
    """Async OHLCV provider for Binance spot markets (paginated forward by startTime)."""

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
        """Fetch OHLCV (timestamp/open/high/low/close/volume).

        With start_date: paginate forward until end_date (or now).
        Without start_date: the latest `limit` bars (ending at end_date if given).
        A bare YYYY-MM-DD end_date covers that whole day.
        """
        client = await self._get_client()
        sym = symbol.replace("/", "").replace("-", "")
        tf_ms = TF_MS.get(timeframe)
        end_ms: Optional[int] = None
        if end_date:
            end_ms = _to_ms(end_date) + (86_400_000 - 1 if len(end_date) == 10 else 0)

        rows: list[list] = []
        try:
            if not start_date or tf_ms is None:
                params: dict = {"symbol": sym, "interval": timeframe, "limit": min(limit, 1000)}
                if end_ms is not None:
                    params["endTime"] = end_ms
                resp = await client.get(f"{self.base_url}/klines", params=params)
                resp.raise_for_status()
                rows = resp.json()
            else:
                cursor = _to_ms(start_date)
                for _ in range(MAX_PAGES):
                    params = {"symbol": sym, "interval": timeframe, "limit": 1000, "startTime": cursor}
                    if end_ms is not None:
                        params["endTime"] = end_ms
                    resp = await client.get(f"{self.base_url}/klines", params=params)
                    resp.raise_for_status()
                    page = resp.json()
                    if not page:
                        break
                    rows.extend(page)
                    cursor = int(page[-1][0]) + tf_ms
                    if len(page) < 1000 or (end_ms is not None and cursor > end_ms):
                        break
        except Exception as e:
            logger.warning("Binance fetch failed for %s: %s", symbol, e)
            if not rows:
                return None

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame([r[:6] for r in rows], columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        return df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
