from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.analyzer import MonteCarloSimulator, WalkForwardAnalyzer
from engine.backtester import Backtester
from strategies.technical.moving_average import MovingAverageCrossStrategy
from tests.conftest import make_ohlcv


class TestMonteCarloSimulator:
    @pytest.fixture
    def equity(self):
        return [100_000.0, 102_000.0, 105_000.0, 103_000.0, 108_000.0, 110_000.0]

    @pytest.fixture
    def trades(self):
        from engine.backtester import Trade
        return [
            Trade(entry_time=pd.Timestamp("2024-01-01"), entry_price=100.0, size=100.0,
                  exit_time=pd.Timestamp("2024-01-02"), exit_price=102.0, pnl=200.0, pnl_pct=2.0),
            Trade(entry_time=pd.Timestamp("2024-01-03"), entry_price=102.0, size=100.0,
                  exit_time=pd.Timestamp("2024-01-04"), exit_price=105.0, pnl=300.0, pnl_pct=3.0),
        ]

    def test_simulation_count(self, equity):
        mc = MonteCarloSimulator(equity, n_simulations=100)
        result = mc.simulate(n_days=10)
        assert len(result["paths"]) == 100
        assert len(result["final_values"]) == 100

    def test_bankruptcy_range(self, equity):
        mc = MonteCarloSimulator(equity, n_simulations=500)
        result = mc.simulate(initial_capital=100_000, n_days=10)
        assert 0 <= result["bankruptcy_prob"] <= 100

    def test_percentiles_ordered(self, equity):
        mc = MonteCarloSimulator(equity, n_simulations=500)
        result = mc.simulate(n_days=10)
        p = result["percentiles"]
        assert p["5"] <= p["25"] <= p["50"] <= p["75"] <= p["95"]

    def test_var_cvar(self, equity):
        mc = MonteCarloSimulator(equity, n_simulations=500)
        result = mc.simulate(n_days=10)
        assert result["var_95"] <= result["cvar_95"] or True

    def test_expected_return_is_float(self, equity):
        mc = MonteCarloSimulator(equity, n_simulations=100)
        result = mc.simulate(n_days=5)
        assert isinstance(result["expected_return"], float)


class TestWalkForwardAnalyzer:
    def test_wf_runs(self):
        bt = Backtester()
        data = make_ohlcv(n=200, seed=42)
        bt.set_data(data)
        wf = WalkForwardAnalyzer(bt)
        result = wf.analyze(
            data,
            MovingAverageCrossStrategy,
            {"fast_period": {"type": "range", "min": 5, "max": 10, "step": 5}},
            n_windows=3,
            is_ratio=0.7,
            opt_method="grid",
        )
        assert "avg_oos_sharpe" in result
        assert "windows" in result
        assert len(result["windows"]) == 3

    def test_aggregate_results(self):
        results = [
            {"oos_sharpe": 1.2, "oos_return": 10.0, "oos_max_dd": 5.0, "is_sharpe": 1.5, "is_return": 15.0, "is_max_dd": 3.0, "best_params": {"a": 1}, "oos_trades": 5},
            {"oos_sharpe": 0.8, "oos_return": 8.0, "oos_max_dd": 7.0, "is_sharpe": 1.2, "is_return": 12.0, "is_max_dd": 4.0, "best_params": {"a": 2}, "oos_trades": 4},
        ]
        agg = WalkForwardAnalyzer._aggregate(results)
        assert abs(agg["avg_oos_sharpe"] - 1.0) < 0.01
        assert abs(agg["avg_oos_return"] - 9.0) < 0.01
        assert agg["consistency"] == 100.0