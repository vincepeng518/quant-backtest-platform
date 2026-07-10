from __future__ import annotations

import pytest

from engine.optimizer import Optimizer
from engine.backtester import Backtester
from strategies.technical.moving_average import MovingAverageCrossStrategy


@pytest.mark.asyncio
async def test_grid_search():
    bt = Backtester()
    s = MovingAverageCrossStrategy()
    s.init({"fast_period": 10, "slow_period": 30})
    bt.set_strategy(s)

    import pandas as pd

    dates = pd.date_range("2024-01-01", periods=200, freq="h")
    data = pd.DataFrame(
        {
            "timestamp": dates,
            "open": [100 + i * 0.3 for i in range(200)],
            "high": [101 + i * 0.3 for i in range(200)],
            "low": [99 + i * 0.3 for i in range(200)],
            "close": [100 + i * 0.3 for i in range(200)],
            "volume": [1000] * 200,
        }
    )
    bt.set_data(data)

    opt = Optimizer(bt, metric="sharpe_ratio")
    space = {"fast_period": {"type": "range", "min": 5, "max": 20, "step": 5}}
    results = opt.grid_search(space)
    assert len(results) > 0
    assert "params" in results[0]
    assert "score" in results[0]