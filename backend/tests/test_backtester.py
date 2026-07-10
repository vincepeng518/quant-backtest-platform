from __future__ import annotations

import pytest

from engine.backtester import Backtester
from strategies.technical.moving_average import MovingAverageCrossStrategy
from strategies.base import Bar


@pytest.mark.asyncio
async def test_backtester_runs():
    bt = Backtester(initial_capital=10_000, commission=0.001, slippage=0.0005)
    s = MovingAverageCrossStrategy()
    s.init({"fast_period": 3, "slow_period": 6})
    bt.set_strategy(s)

    import pandas as pd

    dates = pd.date_range("2024-01-01", periods=100, freq="h")
    data = pd.DataFrame(
        {
            "timestamp": dates,
            "open": [100 + i * 0.5 for i in range(100)],
            "high": [101 + i * 0.5 for i in range(100)],
            "low": [99 + i * 0.5 for i in range(100)],
            "close": [100 + i * 0.5 for i in range(100)],
            "volume": [1000] * 100,
        }
    )
    bt.set_data(data)
    result = await bt.run()
    assert result.total_trades >= 0
    assert result.total_return_pct != 0 or result.total_trades == 0
    assert len(result.equity_curve) == 101  # initial + 100 bars