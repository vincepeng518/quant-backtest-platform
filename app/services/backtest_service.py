from __future__ import annotations

import asyncio
from typing import Any

import pandas as pd

from app.services.data_service import DataService, _backtest_tasks, _execute_backtest, create_task_id
from app.services.strategy_service import get_strategy
from engine.backtester import Backtester


class BacktestService:
    def __init__(self) -> None:
        self.data_service = DataService()

    async def run(self, config: dict[str, Any]) -> dict:
        task_id = create_task_id()
        bt = Backtester(
            initial_capital=config.get("initial_capital", 100_000),
            commission=config.get("commission", 0.001),
            slippage=config.get("slippage", 0.0005),
        )

        # Load data
        data = await self.data_service.get_ohlcv(
            symbol=config.get("symbol", ""),
            timeframe=config.get("timeframe", "1h"),
            start_date=config.get("start_date", ""),
            end_date=config.get("end_date", ""),
            source=config.get("source", "bingx"),
        )
        if data.empty:
            return {"task_id": task_id, "status": "error", "error": "No data"}
        bt.set_data(data)

        # Setup strategy
        strategy_cfg = config.get("strategy", {})
        cls = get_strategy(strategy_cfg.get("template_id", "ma_cross"))
        strategy = cls()
        strategy.init(strategy_cfg.get("params", {}))
        bt.set_strategy(strategy)

        _backtest_tasks[task_id] = {"status": "running", "backtester": bt}
        asyncio.create_task(_execute_backtest(task_id, bt, _backtest_tasks))
        return {"task_id": task_id, "status": "running"}

    def get_status(self, task_id: str) -> dict:
        task = _backtest_tasks.get(task_id)
        if not task:
            return {"task_id": task_id, "status": "error", "error": "Not found"}
        return {"task_id": task_id, "status": task["status"], "progress": 50.0 if task["status"] == "running" else 100.0}

    def get_results(self, task_id: str) -> dict:
        task = _backtest_tasks.get(task_id)
        if not task:
            return {"task_id": task_id, "status": "error", "error": "Not found"}
        if task["status"] != "completed":
            return {"task_id": task_id, "status": task["status"], "error": "Not ready"}
        r = task["result"]
        return {
            "task_id": task_id,
            "status": "completed",
            "metrics": {
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
            "equity_curve": r.equity_curve,
            "trades": [
                {
                    "entry_time": str(t.entry_time),
                    "entry_price": t.entry_price,
                    "exit_time": str(t.exit_time) if t.exit_time else None,
                    "exit_price": t.exit_price,
                    "size": t.size,
                    "pnl": t.pnl,
                    "pnl_pct": t.pnl_pct,
                }
                for t in r.trades
            ],
        }