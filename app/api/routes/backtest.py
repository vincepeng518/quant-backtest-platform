from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
        strat = cfg.get("strategy_id")
        if not strat and isinstance(cfg.get("strategy"), dict):
            strat = cfg["strategy"].get("template_id")
        items.append({
            "task_id": d.get("task_id"),
            "status": d.get("status"),
            "created_at": d.get("created_at"),
            "strategy": strat,
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


def _result_to_out(task_id: str, result, config: dict | None = None) -> BacktestResultOut:
    """Convert an in-memory BacktestResult dataclass to BacktestResultOut.

    The dataclass stores Trade.entry_time/exit_time as pd.Timestamp, which
    pydantic v2 will not auto-coerce to str -> we stringify explicitly.
    Metrics live as flat fields on the dataclass (not a nested dict).
    equity_curve / buy_hold_curve are aligned with `timestamps` and emitted as
    {time, equity} point arrays (frontend charts need a time axis).
    """
    from dataclasses import asdict as _asdict

    def _ts(v):
        return str(v) if v is not None else None

    def _to_unix(v):
        if v is None:
            return None
        try:
            return int(pd.Timestamp(v).timestamp())
        except Exception:
            return None

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
            "direction": getattr(t, "direction", "long"),
            "exit_reason": getattr(t, "exit_reason", ""),
            "holding_bars": getattr(t, "holding_bars", 0),
        }
        for t in r.trades
    ]
    _ts_list = getattr(r, "timestamps", []) or []
    equity_curve = [
        {"time": _to_unix(ts), "equity": float(eq)}
        for ts, eq in zip(_ts_list, r.equity_curve)
        if _to_unix(ts) is not None
    ]
    buy_hold_curve = [
        {"time": _to_unix(ts), "equity": float(eq)}
        for ts, eq in zip(_ts_list, getattr(r, "buy_hold_curve", []) or [])
        if _to_unix(ts) is not None
    ]
    position_status = getattr(r, "position_status", []) or []
    return BacktestResultOut(
        task_id=task_id,
        status="completed",
        config=config or {},
        metrics={
            "total_trades": r.total_trades,
            "winning_trades": r.winning_trades,
            "losing_trades": r.losing_trades,
            "win_rate": r.win_rate,
            "total_return_pct": r.total_return_pct,
            "max_drawdown": r.max_drawdown,
            "max_drawdown_pct": r.max_drawdown_pct,
            "sharpe_ratio": r.sharpe_ratio,
            "sortino_ratio": r.sortino_ratio,
            "profit_factor": r.profit_factor,
            "avg_trade": r.avg_trade,
            "avg_winner": r.avg_winner,
            "avg_loser": r.avg_loser,
            "net_profit": float(r.total_pnl),
            "largest_loss": r.largest_loss,
            "largest_loss_pct": r.largest_loss_pct,
            "largest_win": r.largest_win,
            "win_loss_ratio": r.win_loss_ratio,
            "expectancy": r.expectancy,
            "annual_return_pct": r.annual_return_pct,
            "calmar_ratio": r.calmar_ratio,
            "avg_holding_bars": r.avg_holding_bars,
            "trade_freq": r.trade_freq,
        },
        equity_curve=equity_curve,
        buy_hold_equity=buy_hold_curve,
        trades=trades,
        position_status=position_status,
    )


@router.get("/results/{task_id}", response_model=BacktestResultOut)
async def get_results(task_id: str):
    task = _backtest_tasks.get(task_id)
    if task and task.get("result") is not None:
        return _result_to_out(task_id, task["result"], task.get("config"))
    bd = BACKTESTS_DIR
    fp = bd / f"{task_id}.json"
    if fp.exists():
        d = json.loads(fp.read_text())
        return BacktestResultOut(
            task_id=task_id,
            status=d.get("status", "completed"),
            config=d.get("config", {}),
            metrics=d.get("metrics", {}),
            equity_curve=d.get("equity_curve", []),
            trades=d.get("trades", []),
        )
    raise HTTPException(status_code=404, detail="task not found")


class PushNotionRequest(BaseModel):
    task_id: str
    symbol: str = ""
    strategy: str = ""
    timeframe: str = ""


@router.post("/push-notion")
async def push_notion(req: PushNotionRequest):
    """推送回測結果到 Notion ATM 頁。若未設 NOTION_ATM_PAGE_ID 則靜默跳過。"""
    from app.services.notion_service import push as push_notion_svc
    fp = BACKTESTS_DIR / f"{req.task_id}.json"
    if not fp.exists():
        raise HTTPException(status_code=404, detail="task not found")
    d = json.loads(fp.read_text())
    ok = push_notion_svc(
        {"metrics": d.get("metrics", {}), "trades": d.get("trades", [])},
        req.symbol or d.get("config", {}).get("symbol", "?"),
        req.strategy or d.get("config", {}).get("strategy", {}).get("template_id", "?"),
        req.timeframe or d.get("config", {}).get("timeframe", "?"),
    )
    return {"ok": ok, "notion_configured": bool(os.getenv("NOTION_ATM_PAGE_ID"))}
