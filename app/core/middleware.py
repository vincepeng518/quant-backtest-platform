from __future__ import annotations

import logging
import os
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.access import decide, is_always_public

logger = logging.getLogger("api")


class AccessGuardMiddleware(BaseHTTPMiddleware):
    """全域 API 分級守門（見 app/core/access.py）。

    在路由之前擋掉不該公開的請求，避免逐端點補 Depends 時漏掉。
    帶 x-monitor-key 的機器請求由 decide() 放行，實際 key 驗證仍由端點自己做
    （此處只判斷「有沒有帶」，不取代端點的常數時間比對）。
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if is_always_public(path):
            return await call_next(request)

        bearer = os.getenv("API_BEARER_TOKEN") or ""
        auth = request.headers.get("authorization") or ""
        authenticated = bool(bearer) and auth.startswith("Bearer ") and auth.split(" ", 1)[1].strip() == bearer
        has_machine_key = bool(request.headers.get("x-monitor-key"))

        verdict = decide(request.method, path, authenticated, has_machine_key)
        if verdict == "deny":
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        request.state.ephemeral = verdict == "ephemeral"
        request.state.authenticated = authenticated
        return await call_next(request)


class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = (time.perf_counter() - start) * 1000
        logger.info(f"{request.method} {request.url.path} - {elapsed:.1f}ms")
        response.headers["X-Process-Time-Ms"] = f"{elapsed:.1f}"
        # Security headers
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-XSS-Protection", "1; mode=block")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response