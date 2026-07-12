from __future__ import annotations

import time

import numpy as np
import pytest

from engine.backtester import Backtester
from engine.optimizer import Optimizer
from engine.analyzer import MonteCarloSimulator
from strategies.technical.moving_average import MovingAverageCrossStrategy
from tests.conftest import make_ohlcv


class TestPerformance:
    @pytest.mark.slow
    def test_10_years_backtest(self):
        data = make_ohlcv(n=3650, freq="D", seed=42)
        bt = Backtester(initial_capital=100_000, commission=0.001, slippage=0.0005)
        s = MovingAverageCrossStrategy()
        s.init({"fast_period": 10, "slow_period": 30})
        bt.set_strategy(s)
        bt.set_data(data)

        start = time.perf_counter()
        result = bt.run()
        elapsed = time.perf_counter() - start

        print(f"10-year backtest: {elapsed:.3f}s, {len(data)} bars, {result.total_trades} trades")
        assert elapsed < 5.0, f"Took {elapsed:.2f}s, limit 5s"

    @pytest.mark.slow
    def test_grid_search_100_trials(self):
        data = make_ohlcv(n=500, freq="h", seed=42)
        bt = Backtester()
        s = MovingAverageCrossStrategy()
        s.init({})
        bt.set_strategy(s)
        bt.set_data(data)

        opt = Optimizer(bt, metric="sharpe_ratio")
        space = {
            "fast_period": {"type": "range", "min": 5, "max": 20, "step": 5},
            "slow_period": {"type": "range", "min": 20, "max": 40, "step": 5},
        }

        start = time.perf_counter()
        results = opt.grid_search(space)
        elapsed = time.perf_counter() - start

        print(f"Grid search ({len(results)} combos): {elapsed:.3f}s")
        assert elapsed < 15.0, f"Took {elapsed:.2f}s, limit 15s"

    @pytest.mark.slow
    def test_mc_simulation_1000(self):
        eq = [100_000.0]
        for _ in range(252):
            eq.append(eq[-1] * (1 + np.random.normal(0.0005, 0.015)))

        mc = MonteCarloSimulator(eq, n_simulations=1000)
        start = time.perf_counter()
        result = mc.simulate(n_days=252)
        elapsed = time.perf_counter() - start

        print(f"Monte Carlo (1000 sims): {elapsed:.3f}s")
        assert elapsed < 10.0, f"Took {elapsed:.2f}s, limit 10s"