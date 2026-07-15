"""In-memory synthetic test OHLCV generator.

Used by DataService when source="test" so offline backtests never depend on
disk CSV state or network. Mirrors scripts/gen_test_data.py output.

Supports arbitrary minute/hour timeframes (e.g. 15m, 45m, 1h) so the
generated series actually matches the requested interval — previously this
always emitted 1h bars regardless of the requested timeframe, which made
15m/30m backtests silently run on 1h data.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# timeframe string -> minutes per bar
_TF_MINUTES = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30, "45m": 45,
    "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720,
    "1d": 1440, "3d": 4320, "1w": 10080,
}


def _tf_to_minutes(timeframe: str) -> int:
    if timeframe in _TF_MINUTES:
        return _TF_MINUTES[timeframe]
    # fallback: parse "<N>m" / "<N>h"
    if timeframe.endswith("m"):
        try: return int(timeframe[:-1])
        except ValueError: return 60
    if timeframe.endswith("h"):
        try: return int(timeframe[:-1]) * 60
        except ValueError: return 60
    if timeframe.endswith("d"):
        try: return int(timeframe[:-1]) * 1440
        except ValueError: return 1440
    return 60


def generate_test_data(
    symbol: str,
    timeframe: str = "1h",
    n: Optional[int] = None,
    seed: int = 42,
) -> Optional[pd.DataFrame]:
    """Return an n-row OHLCV DataFrame at the given `timeframe`.

    `n` defaults to roughly one year of bars, capped at 20000 to keep memory
    bounded for sub-hour intervals.
    """
    minutes = _tf_to_minutes(timeframe)
    if n is None:
        # ~1 year, but cap so 1m doesn't explode
        n = int(365 * 24 * 60 / minutes)
        n = max(2000, min(n, 20000))

    rng = np.random.default_rng(seed)
    start = datetime(2025, 1, 1, 0, 0, 0)
    times = [start + timedelta(minutes=minutes * i) for i in range(n)]
    mu, sigma = 0.3 / 8760, 0.02
    base = rng.normal(mu, sigma, n)

    if symbol == "BTC_USDT":
        close = np.maximum(40000 * np.exp(np.cumsum(base)), 1000)
    elif symbol == "ETH_USDT":
        own = rng.normal(mu, sigma, n)
        close = np.maximum(2200 * np.exp(np.cumsum(0.7 * base + 0.3 * own)), 50)
    else:  # SOL_USDT (default / unknown)
        own = rng.normal(mu, sigma, n)
        close = np.maximum(95 * np.exp(np.cumsum(0.6 * base + 0.4 * own)), 5)

    open_p = np.concatenate([[close[0]], close[:-1]])
    noise = np.abs(rng.normal(0, close * 0.003))
    high = np.maximum(open_p, close) + noise
    low = np.maximum(np.minimum(open_p, close) - noise, close * 0.5)
    vol = rng.uniform(100, 2000, n) * (close / 1000)

    return pd.DataFrame(
        {
            "timestamp": [t.strftime("%Y-%m-%d %H:%M:%S") for t in times],
            "open": np.round(open_p, 2),
            "high": np.round(high, 2),
            "low": np.round(low, 2),
            "close": np.round(close, 2),
            "volume": np.round(vol, 4),
        }
    )
