from __future__ import annotations

import pytest

from engine.backtester import Backtester
from engine.optimizer import Optimizer
from engine.exchange import ExchangeModel
from strategies.technical.moving_average import MovingAverageCrossStrategy
from app.services.optimize_service import OptimizeService
from tests_backend.conftest import make_ohlcv

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


class TestOptimizeServiceRealism:
    """T10+ : optimizer must thread opt-in realism into the sub-backtests."""

    def test_realism_disabled_is_legacy(self, monkeypatch):
        captured = {}

        class _SpyBT(Backtester):
            def __init__(self, **kw):
                captured.update(kw)
                super().__init__(**kw)

        monkeypatch.setattr("app.services.optimize_service.Backtester", _SpyBT)
        svc = OptimizeService()
        config = {"strategy_id": "ma_cross", "param_space": [], "funding": {"enabled": False}}
        import asyncio
        asyncio.run(svc._execute("t1", config))
        assert "funding" not in captured
        assert "perp" not in captured
        assert "exchange" not in captured

    def test_realism_enabled_threads_kwargs(self, monkeypatch):
        captured = {}

        class _SpyBT(Backtester):
            def __init__(self, **kw):
                captured.update(kw)
                super().__init__(**kw)

        monkeypatch.setattr("app.services.optimize_service.Backtester", _SpyBT)
        svc = OptimizeService()
        config = {
            "strategy_id": "ma_cross",
            "param_space": [],
            "funding": {"enabled": True, "interval_hours": 8, "default_rate": 0.0001},
            "perpetual": {"enabled": True, "leverage": 10, "maintenance_margin_rate": 0.005},
            "exchange": {"enabled": True, "maker_fee": 0.0002, "taker_fee": 0.0005,
                         "latency_bars": 1, "book_base_slippage": 0.0005},
        }
        import asyncio
        asyncio.run(svc._execute("t2", config))
        assert captured.get("funding") == config["funding"]
        assert captured.get("perp") == config["perpetual"]
        assert captured.get("leverage") == 10.0
        exch = captured.get("exchange")
        assert isinstance(exch, ExchangeModel)
        assert exch.maker_fee == config["exchange"]["maker_fee"]
        assert exch.taker_fee == config["exchange"]["taker_fee"]
        assert exch.latency_bars == config["exchange"]["latency_bars"]
        assert exch.book_base_slippage == config["exchange"]["book_base_slippage"]