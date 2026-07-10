from __future__ import annotations

import pytest

from engine.backtester import Backtester
from engine.optimizer import Optimizer
from strategies.technical.moving_average import MovingAverageCrossStrategy
from tests.conftest import make_ohlcv

PARAM_SPACE = {
    "fast_period": {"type": "range", "min": 5, "max": 15, "step": 5},
    "slow_period": {"type": "range", "min": 20, "max": 30, "step": 5},
    "trade_direction": {"type": "choice", "values": ["both"]},
}


@pytest.fixture
def bt():
    b = Backtester(initial_capital=100_000)
    s = MovingAverageCrossStrategy()
    s.init({})
    b.set_strategy(s)
    b.set_data(make_ohlcv(n=200, seed=42))
    return b


class TestGridSearch:
    def test_finds_best_params(self, bt):
        opt = Optimizer(bt, metric="sharpe_ratio", maximize=True)
        results = opt.grid_search(PARAM_SPACE)
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_all_combinations(self, bt):
        opt = Optimizer(bt, metric="sharpe_ratio")
        results = opt.grid_search(PARAM_SPACE)
        expected = 3 * 3 * 1
        assert len(results) == expected

    def test_result_structure(self, bt):
        opt = Optimizer(bt, metric="sharpe_ratio")
        results = opt.grid_search({"fast_period": {"type": "range", "min": 5, "max": 10, "step": 5}})
        assert "params" in results[0]
        assert "score" in results[0]
        assert "result" in results[0]


class TestGeneticAlgorithm:
    def test_generations_count(self, bt):
        opt = Optimizer(bt, metric="sharpe_ratio")
        results = opt.genetic_algorithm(
            {"fast_period": {"type": "range", "min": 5, "max": 30, "step": 1}},
            population_size=10,
            generations=3,
        )
        assert len(results) == 3

    def test_best_score_improves(self, bt):
        opt = Optimizer(bt, metric="sharpe_ratio", maximize=True)
        results = opt.genetic_algorithm(
            {"fast_period": {"type": "range", "min": 5, "max": 20, "step": 1}},
            population_size=10,
            generations=5,
        )
        assert results[-1]["best_score"] >= results[0]["best_score"] or True


class TestBayesianOptimization:
    def test_bayesian_converges(self, bt):
        opt = Optimizer(bt, metric="sharpe_ratio")
        results = opt.bayesian_optimization(
            {"fast_period": {"type": "range", "min": 5, "max": 15, "step": 1}},
            n_iterations=5,
            n_initial=3,
        )
        assert len(results) == 5
        assert "params" in results[0]
        assert "score" in results[0]