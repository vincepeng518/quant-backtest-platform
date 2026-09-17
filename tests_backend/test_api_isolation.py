"""Task 2/3 — API 隔離與認證測試。

背景：recon 發現 `auth_required()` 在 `API_BEARER_TOKEN` 未設時直接 return
（fail-open），導致無 token 可打 `/api/admin/*`、`/api/backtest/history` 等。
本檔先寫失敗測試，再實作 fail-closed 與端點分級。
"""

from __future__ import annotations

import importlib

import pytest
from fastapi import HTTPException


# ─────────────────────────────────────────────────────────────
# Task 2: fail-closed
# ─────────────────────────────────────────────────────────────


def test_auth_fails_closed_when_token_unset(monkeypatch):
    """未設 API_BEARER_TOKEN 且未開 ALLOW_ANONYMOUS_API → 必須拒絕（503）。"""
    monkeypatch.delenv("API_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("ALLOW_ANONYMOUS_API", raising=False)
    from app.core import auth as auth_mod

    importlib.reload(auth_mod)
    with pytest.raises(HTTPException) as exc:
        auth_mod.auth_required(authorization=None)
    assert exc.value.status_code == 503


def test_auth_allows_explicit_anonymous_optin(monkeypatch):
    """顯式開 ALLOW_ANONYMOUS_API=1（本機開發）才放行。"""
    monkeypatch.delenv("API_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("ALLOW_ANONYMOUS_API", "1")
    from app.core import auth as auth_mod

    importlib.reload(auth_mod)
    assert auth_mod.auth_required(authorization=None) is None


def test_auth_rejects_missing_header_when_configured(monkeypatch):
    monkeypatch.setenv("API_BEARER_TOKEN", "secret-token-abc")
    monkeypatch.delenv("ALLOW_ANONYMOUS_API", raising=False)
    from app.core import auth as auth_mod

    importlib.reload(auth_mod)
    with pytest.raises(HTTPException) as exc:
        auth_mod.auth_required(authorization=None)
    assert exc.value.status_code == 401


def test_auth_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("API_BEARER_TOKEN", "secret-token-abc")
    from app.core import auth as auth_mod

    importlib.reload(auth_mod)
    with pytest.raises(HTTPException) as exc:
        auth_mod.auth_required(authorization="Bearer nope")
    assert exc.value.status_code == 401


def test_auth_accepts_correct_token(monkeypatch):
    monkeypatch.setenv("API_BEARER_TOKEN", "secret-token-abc")
    from app.core import auth as auth_mod

    importlib.reload(auth_mod)
    assert auth_mod.auth_required(authorization="Bearer secret-token-abc") is None


def test_owner_id_is_stable_and_token_specific():
    """owner_id 必須穩定（同 token 同 id）且不同 token 不同 id。"""
    from app.core import auth as auth_mod

    a = auth_mod.owner_id_for("token-A")
    b = auth_mod.owner_id_for("token-A")
    c = auth_mod.owner_id_for("token-B")
    assert a == b
    assert a != c
    assert len(a) >= 8


# ─────────────────────────────────────────────────────────────
# Task 3: 端點分級 + owner 隔離
# ─────────────────────────────────────────────────────────────


@pytest.fixture
def client(monkeypatch):
    """TestClient，token 固定，避免依賴本機 .env。"""
    monkeypatch.setenv("API_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("PUBLIC_MODE", "demo")
    from fastapi.testclient import TestClient

    import app.main as main_mod

    importlib.reload(main_mod)
    return TestClient(main_mod.app)


AUTH = {"Authorization": "Bearer test-token"}


def test_history_requires_auth(client):
    """未認證不得讀回測歷史（原本無 token 可讀全部 27 筆）。"""
    assert client.get("/api/backtest/history").status_code == 401


def test_admin_requires_auth(client):
    assert client.get("/api/admin/overview").status_code == 401
    assert client.get("/api/admin/credentials").status_code == 401


def test_data_import_requires_auth(client):
    assert client.post("/api/data/import", json={}).status_code == 401


def test_chat_requires_auth(client):
    assert client.post("/api/chat/stream", json={"messages": []}).status_code == 401


def test_public_endpoints_still_open(client):
    """公開唯讀端點不受影響（demo 模式）。"""
    assert client.get("/health").status_code == 200
    r = client.get("/api/data/symbols")
    assert r.status_code == 200


def test_health_open_even_in_private_mode(monkeypatch):
    monkeypatch.setenv("API_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("PUBLIC_MODE", "private")
    from fastapi.testclient import TestClient

    import app.main as main_mod

    importlib.reload(main_mod)
    c = TestClient(main_mod.app)
    assert c.get("/health").status_code == 200
    assert c.get("/api/backtest/history").status_code == 401
    # private 模式連公開資料端點都擋
    assert c.get("/api/data/symbols").status_code == 401


def test_owner_isolation_results_404(client):
    """他人 task 的 results 回 404（不洩漏存在性）。"""
    r = client.get("/api/backtest/results/nonexistent-id", headers=AUTH)
    assert r.status_code == 404

