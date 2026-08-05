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
    # Defense-in-depth: sandbox-check custom_code even if not currently exec'd,
    # so a future execution path can't RCE. Mirrors strategy/upload validation.
    if config.strategy.custom_code:
        from app.core.sandbox import check_strategy_code
        ok, err = check_strategy_code(config.strategy.custom_code)
        if not ok:
            raise HTTPException(status_code=400, detail=f"Strategy rejected: {err}")
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
            "quality_score": m.get("quality_score"),
            "quality_grade": m.get("quality_grade"),
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
    # ── Quality score 兜底: 若 backtester 未計算 (舊代碼), API 層補算 ──
    q_score = getattr(r, "quality_score", None)
    q_grade = getattr(r, "quality_grade", None)
    q_breakdown = getattr(r, "quality_breakdown", None)
    # 0.0 也視為未計算 (dataclass 預設值), 除非真的 0 筆交易
    if q_score is None or (q_score == 0.0 and r.total_trades > 0):
        try:
            from engine.backtester import compute_quality_score
            _w = [t.pnl for t in r.trades if t.pnl is not None and t.pnl > 0]
            _l = [t.pnl for t in r.trades if t.pnl is not None and t.pnl < 0]
            _pf = (abs(sum(_w) / sum(_l)) if _l
                   else (999.0 if _w else 0.0))
            q_score, q_grade, q_breakdown = compute_quality_score(
                sharpe=r.sharpe_ratio,
                profit_factor=_pf,
                win_rate=r.win_rate,
                max_drawdown_pct=r.max_drawdown_pct,
                total_trades=r.total_trades,
            )
        except Exception:
            from engine.backtester import _EMPTY_BREAKDOWN
            q_score, q_grade, q_breakdown = 0.0, "F", {**_EMPTY_BREAKDOWN, "penalty_reason": "兜底計算異常"}
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
            "quality_score": q_score,
            "quality_grade": q_grade,
            "quality_breakdown": q_breakdown or {},
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
        metrics = dict(d.get("metrics", {}))
        # 兜底: 舊 JSON 無 quality_score 時補算
        m_qs = metrics.get("quality_score")
        if m_qs is None or (m_qs == 0.0 and (metrics.get("total_trades") or 0) > 0):
            try:
                from engine.backtester import compute_quality_score
                trades = d.get("trades", [])
                _w = [t.get("pnl") for t in trades if t.get("pnl") is not None and t.get("pnl") > 0]
                _l = [t.get("pnl") for t in trades if t.get("pnl") is not None and t.get("pnl") < 0]
                _pf = (abs(sum(_w) / sum(_l)) if _l
                       else (999.0 if _w else 0.0))
                qs, qg, qbrk = compute_quality_score(
                    sharpe=metrics.get("sharpe_ratio") or 0,
                    profit_factor=_pf,
                    win_rate=metrics.get("win_rate") or 0,
                    max_drawdown_pct=metrics.get("max_drawdown_pct") or 0,
                    total_trades=metrics.get("total_trades") or 0,
                )
                metrics["quality_score"] = qs
                metrics["quality_grade"] = qg
                metrics["quality_breakdown"] = qbrk
            except Exception:
                pass
        return BacktestResultOut(
            task_id=task_id,
            status=d.get("status", "completed"),
            config=d.get("config", {}),
            metrics=metrics,
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
    return {"ok": ok, "notion_configured": bool(os.getenv("NOTION_BACKTEST_PAGE_ID"))}
