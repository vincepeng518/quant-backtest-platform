"""Generate synthetic 1y OHLCV test data for offline (source=test) backtests.

BTC/ETH/SOL with light correlation so pairs/stat-arb dual-leg logic has
realistic spread behaviour. Run during build so the container always has
fresh CSV regardless of git/deploy cache state.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
from datetime import datetime, timedelta


def generate(symbol: str, n: int = 8760, seed: int = 42) -> pd.DataFrame:
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
    else:  # SOL_USDT
        own = rng.normal(mu, sigma, n)
        close = np.maximum(95 * np.exp(np.cumsum(0.6 * base + 0.4 * own)), 5)

    open_p = np.concatenate([[close[0]], close[:-1]])
    noise = np.abs(rng.normal(0, close * 0.003))
    high = np.maximum(open_p, close) + noise
    low = np.maximum(np.minimum(open_p, close) - noise, close * 0.5)
    vol = rng.uniform(100, 2000, n) * (close / 1000)

    return pd.DataFrame({
        "timestamp": [t.strftime("%Y-%m-%d %H:%M:%S") for t in times],
        "open": np.round(open_p, 2),
        "high": np.round(high, 2),
        "low": np.round(low, 2),
        "close": np.round(close, 2),
        "volume": np.round(vol, 4),
    })


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(here, "..", "data", "csv")
    os.makedirs(out_dir, exist_ok=True)
    for sym in ["BTC_USDT", "ETH_USDT", "SOL_USDT"]:
        df = generate(sym)
        path = os.path.join(out_dir, f"{sym}.csv")
        df.to_csv(path, index=False)
        print(f"generated {path}: {len(df)} rows")


if __name__ == "__main__":
    main()
