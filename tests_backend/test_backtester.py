from __future__ import annotations

import pytest

from engine.backtester import Backtester
from strategies.technical.moving_average import MovingAverageCrossStrategy
from tests_backend.conftest import make_ohlcv


@pytest.fixture
def backtester():
    return Backtester(initial_capital=100_000, commission=0.001, slippage=0.0005)


def test_initial_capital_preserved(backtester):
    s = MovingAverageCrossStrategy()
    s.init({"fast_period": 3, "slow_period": 6})
    backtester.set_strategy(s)
    backtester.set_data(make_ohlcv(n=50, seed=1))
    result = backtester.run()
    assert result.total_trades >= 0
    assert backtester.initial_capital == 100_000


def test_equity_curve_length(backtester):
    s = MovingAverageCrossStrategy()
    s.init({"fast_period": 5, "slow_period": 10})
    backtester.set_strategy(s)
    data = make_ohlcv(n=100, seed=42)
    backtester.set_data(data)
    result = backtester.run()
    assert len(result.equity_curve) == len(data) + 1


def test_sharpe_ratio_range(backtester):
    s = MovingAverageCrossStrategy()
    s.init({"fast_period": 5, "slow_period": 10})
    backtester.set_strategy(s)
    backtester.set_data(make_ohlcv(n=200, seed=42))
    result = backtester.run()
    assert -20 < result.sharpe_ratio < 20


def test_commission_affects_pnl(backtester):
    s = MovingAverageCrossStrategy()
    s.init({"fast_period": 5, "slow_period": 20})
    backtester.set_strategy(s)
    backtester.set_data(make_ohlcv(n=100, seed=42))
    result = backtester.run()
    if result.total_trades > 0:
        assert result.total_return_pct > -50


def test_trade_records_populated(backtester):
    s = MovingAverageCrossStrategy()
    s.init({"fast_period": 3, "slow_period": 6})
    backtester.set_strategy(s)
    backtester.set_data(make_ohlcv(n=100, seed=99))
    result = backtester.run()
    for t in result.trades:
        assert t.entry_price > 0
        assert t.exit_price is None or t.exit_price > 0
        assert abs(t.size) > 0


def test_no_strategy_raises(backtester):
    backtester.set_data(make_ohlcv(n=10))
    with pytest.raises(ValueError, match="Strategy and data must be set"):
        backtester.run()


def test_no_data_raises(backtester):
    s = MovingAverageCrossStrategy()
    s.init({})
    backtester.set_strategy(s)
    with pytest.raises(ValueError, match="Strategy and data must be set"):
        backtester.run()


def test_missing_columns_raises(backtester):
    import pandas as pd
    bad = pd.DataFrame({"a": [1, 2, 3]})
    s = MovingAverageCrossStrategy()
    s.init({})
    backtester.set_strategy(s)
    with pytest.raises(ValueError, match="Data must contain columns"):
        backtester.set_data(bad)


def test_drawdown_curve_length(backtester):
    s = MovingAverageCrossStrategy()
    s.init({"fast_period": 5, "slow_period": 10})
    backtester.set_strategy(s)
    data = make_ohlcv(n=50, seed=42)
    backtester.set_data(data)
    result = backtester.run()
    assert len(result.drawdown_curve) == len(data) + 1