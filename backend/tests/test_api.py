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
async def test_symbols(client):
    resp = await client.get("/api/data/symbols")
    assert resp.status_code == 200
    assert len(resp.json()) > 0


@pytest.mark.asyncio
async def test_strategy_templates(client):
    resp = await client.get("/api/strategy/templates")
    assert resp.status_code == 200
    templates = resp.json()
    assert len(templates) >= 4
    ids = [t["id"] for t in templates]
    assert "ma_cross" in ids
    assert "breakout" in ids
    assert "pairs_trading" in ids
    assert "stat_arb" in ids


@pytest.mark.asyncio
async def test_backtest_run(client):
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