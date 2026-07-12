from __future__ import annotations

import asyncio
from typing import Any

from app.services.data_service import _optimize_tasks, create_task_id
from app.services.strategy_service import get_strategy
from engine.backtester import Backtester
from engine.optimizer import Optimizer


class OptimizeService:
    async def run(self, config: dict[str, Any]) -> dict:
        task_id = create_task_id()
        _optimize_tasks[task_id] = {"status": "running"}
        asyncio.create_task(self._execute(task_id, config))
        return {"task_id": task_id, "status": "running"}

    async def _execute(self, task_id: str, config: dict) -> None:
        try:
            bt = Backtester()
            cls = get_strategy(config.get("strategy_id", "ma_cross"))
            strategy = cls()
            strategy.init({})
            bt.set_strategy(strategy)

            param_space = {}
            for p in config.get("param_space", []):
                param_space[p["name"]] = {"type": "range", "min": p["min_val"], "max": p["max_val"], "step": p["step"]}

            opt = Optimizer(bt, metric="sharpe_ratio")
            if config.get("algorithm") == "bayesian":
                results = opt.bayesian_optimization(param_space, n_iterations=config.get("max_trials", 30))
            elif config.get("algorithm") == "genetic":
                results = opt.genetic_algorithm(param_space)
            else:
                results = opt.grid_search(param_space)

            _optimize_tasks[task_id] = {
                "status": "completed",
                "best_params": results[0]["params"] if results else {},
                "best_score": results[0]["score"] if results else 0.0,
                "trials": [{"params": r["params"], "score": r["score"]} for r in results[:10]],
            }
        except Exception as e:
            _optimize_tasks[task_id] = {"status": "error", "error": str(e)}

    def get_results(self, task_id: str) -> dict:
        task = _optimize_tasks.get(task_id, {})
        return {"task_id": task_id, "status": task.get("status", "error"), **task}