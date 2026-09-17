from __future__ import annotations

import hashlib
import os
from typing import Optional

from fastapi import Header, HTTPException, status

# Solo SaaS: simple Bearer shared-secret.
# ── 安全前提（2026-09-17 修）──
# 舊版在 API_BEARER_TOKEN 未設時直接 return（fail-open），造成無 token 可打
# /api/admin/*、/api/backtest/history 等。現在改為 fail-closed：
#   未設 token + 未顯式開 ALLOW_ANONYMOUS_API → 503（站台設定錯誤）
#   未設 token + ALLOW_ANONYMOUS_API=1        → 放行（僅本機開發）
_BEARER = os.getenv("API_BEARER_TOKEN") or ""
_ALLOW_ANON = os.getenv("ALLOW_ANONYMOUS_API", "0") == "1"

# 匿名身分（PUBLIC_MODE=demo 時公開端點用）
ANON_OWNER = "__anon__"


def _read_env() -> None:
    """測試會 reload 模組；統一在此讀 env 以便 monkeypatch 生效。"""
    global _BEARER, _ALLOW_ANON
    _BEARER = os.getenv("API_BEARER_TOKEN") or ""
    _ALLOW_ANON = os.getenv("ALLOW_ANONYMOUS_API", "0") == "1"


_read_env()


def auth_required(authorization: Optional[str] = Header(default=None)) -> None:
    """Guard for owner-only endpoints.

    Fail-closed：未設定 API_BEARER_TOKEN 時拒絕（除非顯式開匿名）。
    """
    _read_env()
    if not _BEARER:
        if _ALLOW_ANON:
            return
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server auth not configured (API_BEARER_TOKEN unset)",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    if token != _BEARER:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def is_anonymous(authorization: Optional[str] = Header(default=None)) -> bool:
    """True = 未帶有效 token。用於決定是否走 ephemeral（不落庫）路徑。"""
    _read_env()
    if not _BEARER:
        return True
    if not authorization or not authorization.startswith("Bearer "):
        return True
    return authorization.split(" ", 1)[1].strip() != _BEARER


def owner_id_for(token: Optional[str] = None) -> str:
    """由 token 推導穩定的 owner 識別。

    單人站台的近似多租戶：同一 token → 同一 owner_id。
    不是真正的使用者帳號系統（YAGNI）；要真多租戶再上 users 表 + JWT。
    """
    if not token:
        return ANON_OWNER
    return "own_" + hashlib.sha256(token.encode()).hexdigest()[:16]


def current_owner(authorization: Optional[str] = Header(default=None)) -> str:
    """FastAPI 依賴：回傳當前 owner_id（匿名則 __anon__）。"""
    _read_env()
    if _BEARER and authorization and authorization.startswith("Bearer "):
        tok = authorization.split(" ", 1)[1].strip()
        if tok == _BEARER:
            return owner_id_for(tok)
    return ANON_OWNER
