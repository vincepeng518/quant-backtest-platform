from __future__ import annotations

import json
from httpx import AsyncClient, ASGITransport
import pytest

from app.main import app
from app.services import admin_service as admin_mod


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture(autouse=True)
def _tmp_data(tmp_path, monkeypatch):
    """Point AdminService at a temp data dir so tests never touch real data."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BACKTESTS_DIR", str(tmp_path / "backtests"))
    (tmp_path / "backtests").mkdir()
    # Rebind the module-level dirs the service reads from.
    monkeypatch.setattr(admin_mod, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(admin_mod, "_BACKTESTS_DIR", tmp_path / "backtests")
    # The route module instantiates `svc` at import time, so its paths are
    # already bound. Rebuild it now that env/dirs point at the temp dir, and
    # rebind it on the route module so the endpoints use the temp data.
    import app.api.routes.admin as admin_route

    new_svc = admin_mod.AdminService()
    monkeypatch.setattr(admin_route, "svc", new_svc)
    yield tmp_path


@pytest.mark.asyncio
async def test_admin_overview_shape(client):
    resp = await client.get("/api/admin/overview")
    assert resp.status_code == 200
    data = resp.json()
    for key in ("watchlist", "credentials", "task_history", "usage", "config"):
        assert key in data
    assert isinstance(data["watchlist"], list)
    assert isinstance(data["credentials"], list)
    assert isinstance(data["usage"], list)
    assert isinstance(data["config"], dict)


@pytest.mark.asyncio
async def test_admin_credentials_masked(client):
    resp = await client.get("/api/admin/credentials")
    assert resp.status_code == 200
    creds = resp.json()
    assert len(creds) > 0
    for c in creds:
        # plaintext secret must never appear in response
        assert "secret" not in c
        # masked_value can be "" (unset) or a 2***2 preview
        assert c["masked_value"] == "" or "****" in c["masked_value"]


@pytest.mark.asyncio
async def test_admin_watchlist_crud(client):
    # add
    r = await client.post(
        "/api/admin/watchlist",
        json={"symbol": "ETH/USDT", "market": "crypto", "pinned": True},
    )
    assert r.status_code == 201
    sym = r.json()
    assert sym["symbol"] == "ETH/USDT"
    assert sym["pinned"] is True

    # duplicate → 400
    r = await client.post("/api/admin/watchlist", json={"symbol": "ETH/USDT"})
    assert r.status_code == 400

    # toggle pin
    r = await client.post("/api/admin/watchlist/pin", params={"symbol": "ETH/USDT"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    wl = (await client.get("/api/admin/watchlist")).json()
    assert any(s["symbol"] == "ETH/USDT" and s["pinned"] is False for s in wl)

    # missing symbol → 404
    r = await client.delete("/api/admin/watchlist", params={"symbol": "NOPE/USDT"})
    assert r.status_code == 404

    # delete
    r = await client.delete("/api/admin/watchlist", params={"symbol": "ETH/USDT"})
    assert r.status_code == 200
    wl = (await client.get("/api/admin/watchlist")).json()
    assert all(s["symbol"] != "ETH/USDT" for s in wl)


@pytest.mark.asyncio
async def test_admin_config_default_and_patch(client, tmp_path, monkeypatch):
    r = await client.get("/api/admin/config")
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["default_timeframe"] == "1h"
    assert cfg["maintenance_mode"] is False

    # patch partial
    r = await client.patch(
        "/api/admin/config",
        json={"default_timeframe": "4h", "maintenance_mode": True},
    )
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["default_timeframe"] == "4h"
    assert cfg["maintenance_mode"] is True
    # unspecified fields preserved
    assert cfg["default_symbol"] == "BTC/USDT"

    # persisted to disk
    raw = json.loads((tmp_path / "site_config.json").read_text())
    assert raw["default_timeframe"] == "4h"
    assert raw["maintenance_mode"] is True

    # rejected extra field (model forbids extra)
    r = await client.patch("/api/admin/config", json={"bogus": 1})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_admin_task_history_from_files(client, tmp_path, monkeypatch):
    bd = tmp_path / "backtests"
    (bd / "abc12345.json").write_text(
        json.dumps(
            {
                "task_id": "abc12345",
                "status": "completed",
                "created_at": "2024-05-01T00:00:00",
                "config": {"symbol": "BTC/USDT", "timeframe": "1h", "strategy": {"template_id": "ma_cross"}},
                "metrics": {"sharpe_ratio": 1.5, "total_trades": 42},
            }
        )
    )
    r = await client.get("/api/admin/tasks")
    assert r.status_code == 200
    tasks = r.json()
    assert len(tasks) == 1
    t = tasks[0]
    assert t["task_id"] == "abc12345"
    assert t["symbol"] == "BTC/USDT"
    assert t["strategy"] == "ma_cross"
    assert t["score"] == 1.5


@pytest.mark.asyncio
async def test_admin_usage_counts(client, tmp_path, monkeypatch):
    bd = tmp_path / "backtests"
    for i, st in enumerate(["completed", "completed", "error"]):
        (bd / f"run{i}.json").write_text(
            json.dumps(
                {
                    "task_id": f"run{i}",
                    "status": st,
                    "created_at": "2024-05-01T00:00:00",
                    "config": {"symbol": f"SYM{i}/USDT"},
                    "metrics": {"total_trades": 10},
                }
            )
        )
    r = await client.get("/api/admin/usage")
    assert r.status_code == 200
    usage = {u["metric"]: u["value"] for u in r.json()}
    assert usage["total_runs"] == 3
    assert usage["completed_runs"] == 2
    assert usage["failed_runs"] == 1
    assert usage["total_trades"] == 30
    assert usage["unique_symbols"] == 3
