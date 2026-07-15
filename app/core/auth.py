from __future__ import annotations

import os
from typing import Optional

from fastapi import Header, HTTPException, status

# Solo SaaS: simple Bearer shared-secret. If API_BEARER_TOKEN is unset, auth is
# disabled (local/dev convenience). Set it in production to lock owner endpoints.
_BEARER = os.getenv("API_BEARER_TOKEN") or ""


def auth_required(authorization: Optional[str] = Header(default=None)) -> None:
    """Guard for owner-only endpoints. No-op when API_BEARER_TOKEN is unset."""
    if not _BEARER:
        return
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
