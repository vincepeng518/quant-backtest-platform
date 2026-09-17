"""Mock data generators for all tests + 測試環境 auth 設定。"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from engine.backtester import Trade
from strategies.base import Bar

# Task 2/3 起後端 fail-closed：測試統一帶這把固定 token。
TEST_TOKEN = "test-token-isolation"


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch):
    """所有測試預設帶 auth token，避免既有測試因 fail-closed 而 401。"""
    monkeypatch.setenv("API_BEARER_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("PUBLIC_MODE", "demo")


def make_bars(closes: list[float], seed: int = 0) -> list[Bar]:
    """Generate Bar list from close prices, using sequential hours to avoid day overflow."""
    rng = np.random.default_rng(seed)
    base = pd.Timestamp("2024-01-01")
    return [
        Bar(
            timestamp=base + pd.Timedelta(hours=i),
            open=c * (1 + rng.uniform(-0.005, 0.005)),
            high=c * (1 + abs(rng.normal(0, 0.01))),
            low=c * (1 - abs(rng.normal(0, 0.01))),
            close=c,
            volume=float(rng.integers(1000, 10000)),
        )
        for i, c in enumerate(closes)
    ]


def make_ohlcv(n: int = 200, start: str = "2024-01-01", freq: str = "D", seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV DataFrame."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=n, freq=freq)
    prices = 100 + np.cumsum(rng.normal(0, 2, n))
    return pd.DataFrame(
        {
            "timestamp": dates,
            "open": prices + rng.normal(0, 0.5, n),
            "high": prices + np.abs(rng.normal(0, 2, n)),
            "low": prices - np.abs(rng.normal(0, 2, n)),
            "close": prices,
            "volume": rng.integers(1000, 10000, n),
        }
    )


def make_trades(n: int = 5, seed: int = 0) -> list[Trade]:
    """Generate synthetic trade records."""
    rng = np.random.default_rng(seed)
    trades = []
    for i in range(n):
        entry = 100 + rng.uniform(-5, 5)
        ret = rng.uniform(-0.05, 0.08)
        exit_ = entry * (1 + ret)
        size = 1000.0
        trades.append(
            Trade(
                entry_time=pd.Timestamp(f"2024-01-{2*i+1:02d}"),
                entry_price=entry,
                size=size,
                exit_time=pd.Timestamp(f"2024-01-{2*i+2:02d}"),
                exit_price=exit_,
                pnl=size * (exit_ - entry),
                pnl_pct=ret * 100,
            )
        )
    return trades


def make_equity_curve(n: int = 100, start: float = 100_000, seed: int = 0) -> list[float]:
    """Generate synthetic equity curve."""
    rng = np.random.default_rng(seed)
    eq = [start]
    for _ in range(n):
        eq.append(eq[-1] * (1 + rng.normal(0.0005, 0.015)))
    return eq