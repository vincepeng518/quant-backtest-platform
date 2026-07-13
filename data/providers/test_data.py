"""In-memory synthetic test OHLCV generator.

Used by DataService when source="test" so offline backtests never depend on
disk CSV state or network. Mirrors scripts/gen_test_data.py output.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from datetime import datetime, timedelta


def generate_test_data(
    symbol: str, n: int = 8760, seed: int = 42
) -> Optional[pd.DataFrame]:
    """Return an n-row 1h OHLCV DataFrame for the given symbol."""
    rng = np.random.default_rng(seed)
    start = datetime(2025, 1, 1, 0, 0, 0)
    times = [start + timedelta(hours=i) for i in range(n)]
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
