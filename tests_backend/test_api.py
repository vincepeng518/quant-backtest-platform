from __future__ import annotations

from httpx import AsyncClient, ASGITransport
import pytest

from app.main import app


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_root(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert "service" in data
    assert "docs" in data


class TestDataAPI:
    @pytest.mark.asyncio
    async def test_symbols(self, client):
        resp = await client.get("/api/data/symbols")
        assert resp.status_code == 200
        symbols = resp.json()
        assert len(symbols) > 0
        assert "BTC/USDT" in [s["symbol"] for s in symbols]

    @pytest.mark.asyncio
    async def test_ohlcv(self, client):
        resp = await client.get("/api/data/ohlcv?symbol=BTC/USDT&timeframe=1h")
        # May return empty if no data, but status 200
        assert resp.status_code == 200


class TestStrategyAPI:
    @pytest.mark.asyncio
    async def test_templates(self, client):
        resp = await client.get("/api/strategy/templates")
        assert resp.status_code == 200
        templates = resp.json()
        ids = [t["id"] for t in templates]
        assert "ma_cross" in ids
        assert "breakout" in ids
        assert "pairs_trading" in ids
        assert "stat_arb" in ids

    @pytest.mark.asyncio
    async def test_validate(self, client):
        resp = await client.post("/api/strategy/validate")
        assert resp.status_code == 200


class TestBacktestAPI:
    @pytest.mark.asyncio
    async def test_run_backtest(self, client):
        resp = await client.post(
            "/api/backtest/run",
            json={
                "strategy": {"template_id": "ma_cross", "params": {"fast_period": 10, "slow_period": 30}},
                "symbol": "BTC/USDT",
                "timeframe": "1h",
                "initial_capital": 10000,
                "commission": 0.001,
                "slippage": 0.0005,
            },
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "task_id" in data

    @pytest.mark.asyncio
    async def test_validation_422(self, client):
        """Missing required fields → 422."""
        resp = await client.post("/api/backtest/run", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_nonexistent_status(self, client):
        resp = await client.get("/api/backtest/status/nonexistent-id")
        # Our impl returns 200 with error field, not 404
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_nonexistent_results(self, client):
        resp = await client.get("/api/backtest/results/nonexistent-id")
        assert resp.status_code in (200, 404)


class TestOptimizeAPI:
    @pytest.mark.asyncio
    async def test_run_optimize(self, client):
        resp = await client.post(
            "/api/optimize/run",
            json={
                "strategy_id": "ma_cross",
                "param_space": [{"name": "fast_period", "min_val": 5, "max_val": 15, "step": 5}],
                "algorithm": "grid",
                "max_trials": 10,
            },
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "task_id" in data

    @pytest.mark.asyncio
    async def test_apply_best_params(self, client):
        resp = await client.post("/api/optimize/best-params", json={"params": {"fast_period": 10}})
        assert resp.status_code == 200


class TestAnalysisAPI:
    @pytest.mark.asyncio
    async def test_walk_forward(self, client):
        resp = await client.post(
            "/api/analysis/walk-forward",
            json={
                "strategy_id": "ma_cross",
                "symbol": "BTC/USDT",
                "timeframe": "1h",
                "param_space": [{"name": "fast_period", "min_val": 5, "max_val": 10, "step": 5}],
                "n_windows": 2,
            },
        )
        assert resp.status_code == 202

    @pytest.mark.asyncio
    async def test_monte_carlo(self, client):
        resp = await client.post(
            "/api/analysis/monte-carlo",
            json={"equity_curve": [100000, 101000, 102000], "n_simulations": 10},
        )
        assert resp.status_code == 202

    @pytest.mark.asyncio
    async def test_nonexistent_analysis(self, client):
        resp = await client.get("/api/analysis/results/nonexistent")
        assert resp.status_code == 404