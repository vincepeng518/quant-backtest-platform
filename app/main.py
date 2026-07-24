# Railway rebuild trigger - 20260724T2100
from __future__ import annotations

import logging
import os
import sqlite3
import json
from datetime import datetime, timezone

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.routes import data, strategy, backtest, optimize, analysis, arbitrage, monitoring, research, admin, experiments, validate, exchanges, trades
from app.config import settings
from app.core.auth import auth_required
from app.core.exceptions import AppException
from app.core.middleware import TimingMiddleware

logger = logging.getLogger(__name__)
logging.basicConfig(level=settings.log_level.upper())

app = FastAPI(title="Quant Backtest Platform API", version="1.0.0", docs_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
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
app.include_router(monitoring.router)
app.include_router(research.router, prefix="/api")
app.include_router(admin.router)
app.include_router(experiments.router)
app.include_router(validate.router)
app.include_router(exchanges.router)
app.include_router(trades.router)


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
    return {"alive": True, "updated_at": row[1], "data": json.loads(row[0])}
