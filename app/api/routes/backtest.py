from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.models.schemas import BacktestConfig, BacktestResultOut, TaskStatus
from app.services.backtest_service import BacktestService
from app.services.data_service import _backtest_tasks

# Backtests are written by app/services/data_service.py to <repo>/backtests,
# i.e. parents[2] of that module — anchor here so both reader routes agree.
_DATA_SERVICE = __import__("app.services.data_service", fromlist=["__file__"]).__file__
BACKTESTS_DIR = Path(_DATA_SERVICE).resolve().parents[2] / "backtests"

router = APIRouter(prefix="/api/backtest", tags=["backtest"])
svc = BacktestService()


@router.post("/run", status_code=202)
async def run_backtest(config: BacktestConfig):
    return await svc.run(config.model_dump())


@router.get("/history")
async def list_history():
    bd = BACKTESTS_DIR
    if not bd.exists():
        return []
    items = []
    for f in sorted(bd.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        m = d.get("metrics", {}) or {}
        cfg = d.get("config", {}) or {}
        items.append({
            "task_id": d.get("task_id"),
            "status": d.get("status"),
            "created_at": d.get("created_at"),
            "strategy": cfg.get("strategy_id") or cfg.get("template_id"),
            "symbol": cfg.get("symbol"),
            "timeframe": cfg.get("timeframe"),
            "sharpe": m.get("sharpe_ratio"),
            "total_trades": m.get("total_trades"),
        })
    return items


@router.get("/status/{task_id}")
async def get_status(task_id: str):
    s = svc.get_status(task_id)
    return TaskStatus(**s)


def _result_to_out(task_id: str, result) -> BacktestResultOut:
    """Convert an in-memory BacktestResult dataclass to BacktestResultOut.

    The dataclass stores Trade.entry_time/exit_time as pd.Timestamp, which
    pydantic v2 will not auto-coerce to str -> we stringify explicitly.
    Metrics live as flat fields on the dataclass (not a nested dict).
    """
    from dataclasses import asdict as _asdict

    def _ts(v):
        return str(v) if v is not None else None

    r = result
    trades = [
        {
            "entry_time": _ts(t.entry_time),
            "entry_price": t.entry_price,
            "exit_time": _ts(t.exit_time),
            "exit_price": t.exit_price,
            "size": t.size,
            "pnl": t.pnl,
            "pnl_pct": t.pnl_pct,
        }
        for t in r.trades
    ]
    return BacktestResultOut(
        task_id=task_id,
        status="completed",
        metrics={
            "total_trades": r.total_trades,
            "win_rate": r.win_rate,
            "total_return_pct": r.total_return_pct,
            "max_drawdown": r.max_drawdown,
            "sharpe_ratio": r.sharpe_ratio,
            "sortino_ratio": r.sortino_ratio,
            "profit_factor": r.profit_factor,
            "avg_trade": r.avg_trade,
            "avg_winner": r.avg_winner,
            "avg_loser": r.avg_loser,
        },
        equity_curve=list(r.equity_curve),
        trades=trades,
    )


@router.get("/results/{task_id}", response_model=BacktestResultOut)
async def get_results(task_id: str):
    task = _backtest_tasks.get(task_id)
    if task and task.get("result") is not None:
        return _result_to_out(task_id, task["result"])
    bd = BACKTESTS_DIR
    fp = bd / f"{task_id}.json"
    if fp.exists():
        d = json.loads(fp.read_text())
        return BacktestResultOut(
            task_id=task_id,
            status=d.get("status", "completed"),
            metrics=d.get("metrics", {}),
            equity_curve=d.get("equity_curve", []),
            trades=d.get("trades", []),
        )
    raise HTTPException(status_code=404, detail="task not found")
