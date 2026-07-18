from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Depends

from app.core.auth import auth_required

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])

PUSH_KEY = os.getenv("MONITOR_PUSH_KEY", "quant-monitor-local")
_BACKEND_DB = os.getenv("DB_PATH", "./data/backtest.db")
_SHADOW_DB = os.getenv("MONITOR_DB_PATH", "./monitoring/shadow.db")


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_BACKEND_DB)
    c.execute(
        """CREATE TABLE IF NOT EXISTS monitoring_stats (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            payload TEXT,
            updated_at TEXT
        )"""
    )
    return c


def _shadow_conn() -> sqlite3.Connection:
    c = sqlite3.connect(_SHADOW_DB)
    c.row_factory = sqlite3.Row
    return c


@router.post("/push")
async def push(req: Request):
    key = req.headers.get("x-monitor-key", "")
    if key != PUSH_KEY:
        raise HTTPException(status_code=401, detail="bad key")
    body = await req.json()
    import json
    c = _conn()
    try:
        c.execute(
            "INSERT OR REPLACE INTO monitoring_stats (id, payload, updated_at) VALUES (1, ?, ?)",
            (json.dumps(body), datetime.now(timezone.utc).isoformat()),
        )
        c.commit()
    finally:
        c.close()
    return {"ok": True}


@router.get("/stats")
async def stats(_: None = Depends(auth_required)):
    c = _conn()
    try:
        row = c.execute(
            "SELECT payload, updated_at FROM monitoring_stats WHERE id=1"
        ).fetchone()
    finally:
        c.close()
    if not row:
        return {"available": False}
    import json
    return {"available": True, "updated_at": row[1], "data": json.loads(row[0])}


@router.get("/trades")
async def trades(limit: int = 50, _: None = Depends(auth_required)):
    """Shadow trades from monitoring/shadow.db (live daemon)."""
    c = _shadow_conn()
    try:
        rows = c.execute(
            "SELECT * FROM shadow_trades ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        c.close()
    return {"trades": [dict(r) for r in rows], "count": len(rows)}


@router.get("/rounds")
async def rounds(limit: int = 50, _: None = Depends(auth_required)):
    """Round logs (resolved/unresolved) from monitoring/shadow.db."""
    c = _shadow_conn()
    try:
        rows = c.execute(
            "SELECT * FROM round_logs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        c.close()
    return {"rounds": [dict(r) for r in rows], "count": len(rows)}


import json as _json

_RUNTIME_DIR = os.getenv("RUNTIME_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "runtime"))


@router.get("/strategy")
async def strategy_status(_: None = Depends(auth_required)):
    """External strategy live status + order history.

    Strategy script writes runtime/strategy_status.json (summary) and
    appends to runtime/orders.jsonl (one JSON object per line per fill).
    """
    status_path = os.path.join(_RUNTIME_DIR, "strategy_status.json")
    orders_path = os.path.join(_RUNTIME_DIR, "orders.jsonl")

    status = {"running": False, "available": False}
    if os.path.exists(status_path):
        try:
            with open(status_path) as f:
                status = _json.load(f)
                status["available"] = True
        except Exception:
            status = {"running": False, "available": True, "error": "bad json"}

    orders: list[dict] = []
    if os.path.exists(orders_path):
        try:
            with open(orders_path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            orders.append(_json.loads(line))
                        except Exception:
                            pass
        except Exception:
            pass
    # newest first
    orders.reverse()

    return {"status": status, "orders": orders, "count": len(orders)}
