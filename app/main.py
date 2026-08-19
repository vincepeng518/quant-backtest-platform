# Railway rebuild trigger - 20260724T2100
from __future__ import annotations

import logging
import os
import sqlite3
import json
from datetime import datetime, timezone

from fastapi import FastAPI, Request, HTTPException, Depends
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from app.api.routes import data, strategy, backtest, optimize, analysis, arbitrage, monitoring, research, admin, experiments, validate, exchanges, trades, portfolio, realtime_ws, chat
from app.config import settings
from app.core.auth import auth_required
from app.core.exceptions import AppException
from app.core.middleware import TimingMiddleware

logger = logging.getLogger(__name__)
logging.basicConfig(level=settings.log_level.upper())

# Reject oversized request bodies (max 10 MB) before the app reads them — a
# resource-exhaustion / DoS guard. cvxpy/numpy backends will happily parse and
# buffer a 50 MB JSON body and spin for 12+s otherwise.
MAX_BODY_BYTES = int(os.getenv("MAX_BODY_BYTES", "10_000_000"))


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH"):
            cl = request.headers.get("content-length")
            if cl:
                try:
                    if int(cl) > MAX_BODY_BYTES:
                        return Response(
                            json.dumps({"detail": f"Request body too large (max {MAX_BODY_BYTES} bytes)"}),
                            status_code=413,
                            media_type="application/json",
                        )
                except ValueError:
                    pass
        return await call_next(request)


app = FastAPI(title="Quant Backtest Platform API", version="1.0.0", docs_url="/docs", redoc_url=None)


# Redoc served with a pinned CDN version. `redoc@next` is broken (404) and makes
# /redoc render blank. Pin to a known-good release.
_REDOC_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<title>Quant Backtest Platform API - ReDoc</title>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<link rel="shortcut icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📊</text></svg>"/>
<style>body{margin:0;padding:0}</style>
</head>
<body>
<noscript>ReDoc requires Javascript to function.</noscript>
<redoc spec-url="/openapi.json"></redoc>
<script src="https://cdn.jsdelivr.net/npm/redoc@2.2.0/bundles/redoc.standalone.js"></script>
</body>
</html>"""


@app.get("/redoc", include_in_schema=False, response_class=HTMLResponse)
async def redoc():
    return HTMLResponse(_REDOC_HTML)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(TimingMiddleware)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
    )


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/")
async def root():
    return {"service": "Quant Backtest Platform", "docs": "/docs"}


# Mount routes
app.include_router(data.router)
app.include_router(strategy.router)
app.include_router(backtest.router)
app.include_router(optimize.router)
app.include_router(analysis.router)
app.include_router(arbitrage.router)
app.include_router(portfolio.router)
app.include_router(realtime_ws.router)
app.include_router(monitoring.router)
app.include_router(research.router, prefix="/api")
app.include_router(admin.router)
app.include_router(experiments.router)
app.include_router(validate.router)
app.include_router(exchanges.router)
app.include_router(trades.router)
app.include_router(chat.router)


# ── Predict Bot Heartbeat (direct in main.py) ──
PUSH_KEY = os.getenv("MONITOR_PUSH_KEY", "quant-monitor-local")
BACKEND_DB = os.getenv("DB_PATH", "./data/backtest.db")


def _hb_conn() -> sqlite3.Connection:
    c = sqlite3.connect(BACKEND_DB)
    c.execute(
        """CREATE TABLE IF NOT EXISTS predict_heartbeat (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            payload TEXT,
            updated_at TEXT
        )"""
    )
    return c


@app.post("/api/monitoring/heartbeat")
async def post_heartbeat(req: Request):
    """Predict bot heartbeat endpoint."""
    key = req.headers.get("x-monitor-key", "")
    if key != PUSH_KEY:
        raise HTTPException(status_code=401, detail="bad key")
    body = await req.json()
    c = _hb_conn()
    try:
        c.execute(
            "INSERT OR REPLACE INTO predict_heartbeat (id, payload, updated_at) VALUES (1, ?, ?)",
            (json.dumps(body), datetime.now(timezone.utc).isoformat()),
        )
        c.commit()
    finally:
        c.close()
    return {"ok": True}


@app.get("/api/monitoring/heartbeat")
async def get_heartbeat(_: None = Depends(auth_required)):
    """Get predict bot heartbeat status."""
    c = _hb_conn()
    try:
        row = c.execute(
            "SELECT payload, updated_at FROM predict_heartbeat WHERE id=1"
        ).fetchone()
    finally:
        c.close()
    if not row:
        return {"alive": False, "updated_at": None}
    # 衰退閾值：超過 2 小時無 heartbeat → 判定為 dead
    try:
        age_s = (datetime.now(timezone.utc) - datetime.fromisoformat(row[1])).total_seconds()
        if age_s > 7200:
            return {"alive": False, "updated_at": row[1], "data": json.loads(row[0]), "age_s": int(age_s)}
    except Exception:
        pass
    return {"alive": True, "updated_at": row[1], "data": json.loads(row[0])}
