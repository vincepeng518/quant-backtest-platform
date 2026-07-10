from __future__ import annotations

import asyncio
from typing import Any

from app.services.data_service import _analysis_tasks, create_task_id
from app.services.strategy_service import get_strategy
from engine.analyzer import WalkForwardAnalyzer, MonteCarloSimulator
from engine.backtester import Backtester


class AnalysisService:
    async def run_walk_forward(self, config: dict[str, Any]) -> dict:
        task_id = create_task_id()
        _analysis_tasks[task_id] = {"status": "running"}
        asyncio.create_task(self._execute_wf(task_id, config))
        return {"task_id": task_id, "status": "running"}

    async def run_monte_carlo(self, config: dict[str, Any]) -> dict:
        task_id = create_task_id()
        _analysis_tasks[task_id] = {"status": "running"}
        asyncio.create_task(self._execute_mc(task_id, config))
        return {"task_id": task_id, "status": "running"}

    async def _execute_wf(self, task_id: str, config: dict) -> None:
        try:
            bt = Backtester()
            from data.providers.binance import BinanceProvider
            provider = BinanceProvider()
            data = await provider.fetch_ohlcv(config.get("symbol", "BTC/USDT"), config.get("timeframe", "1h"))
            cls = get_strategy(config.get("strategy_id", "ma_cross"))
            param_space = {}
            for p in config.get("param_space", []):
                param_space[p["name"]] = {"type": "range", "min": p["min_val"], "max": p["max_val"], "step": p["step"]}

            wf = WalkForwardAnalyzer(bt)
            result = wf.analyze(
                data, cls, param_space, n_windows=config.get("n_windows", 5), opt_method=config.get("algorithm", "grid")
            )
            _analysis_tasks[task_id] = {"status": "completed", "result": result}
        except Exception as e:
            _analysis_tasks[task_id] = {"status": "error", "error": str(e)}

    async def _execute_mc(self, task_id: str, config: dict) -> None:
        try:
            eq = config.get("equity_curve", [1000])
            mc = MonteCarloSimulator(eq, n_simulations=config.get("n_simulations", 500))
            result = mc.simulate(initial_capital=config.get("initial_capital", 100_000))
            _analysis_tasks[task_id] = {"status": "completed", "result": result}
        except Exception as e:
            _analysis_tasks[task_id] = {"status": "error", "error": str(e)}

    def get_results(self, task_id: str) -> dict:
        task = _analysis_tasks.get(task_id, {})
        r = task.get("result", {})
        return {
            "task_id": task_id,
            "status": task.get("status", "error"),
            "summary": r if isinstance(r, dict) else {},
        }