from __future__ import annotations

import asyncio
from typing import Any

from app.services.data_service import DataService, _optimize_tasks, create_task_id
from app.services.strategy_service import get_strategy
from engine.backtester import Backtester
from engine.optimizer import Optimizer


class OptimizeService:
    def __init__(self) -> None:
        self.data_service = DataService()

    async def _load_data(self, config: dict) -> Any:
        return await self.data_service.get_ohlcv(
            symbol=config.get("symbol", "BTC/USDT"),
            timeframe=config.get("timeframe", "1h"),
            start_date=config.get("start_date", ""),
            end_date=config.get("end_date", ""),
        )

    async def run(self, config: dict[str, Any]) -> dict:
        task_id = create_task_id()
        _optimize_tasks[task_id] = {"status": "running"}
        asyncio.create_task(self._execute(task_id, config))
        return {"task_id": task_id, "status": "running"}

    async def _execute(self, task_id: str, config: dict) -> None:
        try:
            # Build opt-in realism kwargs (only when enabled — disabled = legacy 1x spot)
            bt_kwargs: dict[str, Any] = {}
            funding_cfg = config.get("funding") or {}
            perp_cfg = config.get("perpetual") or {}
            exch_cfg = config.get("exchange") or {}
            if funding_cfg.get("enabled"):
                bt_kwargs["funding"] = funding_cfg
            if perp_cfg.get("enabled"):
                bt_kwargs["perp"] = perp_cfg
                bt_kwargs["leverage"] = float(perp_cfg.get("leverage", 1.0))
            if exch_cfg.get("enabled"):
                try:
                    from engine.exchange import ExchangeModel
                    bt_kwargs["exchange"] = ExchangeModel(
                        maker_fee=exch_cfg.get("maker_fee", 0.0002),
                        taker_fee=exch_cfg.get("taker_fee", 0.0005),
                        latency_bars=int(exch_cfg.get("latency_bars", 0)),
                        book_base_slippage=exch_cfg.get("book_base_slippage", 0.0005),
                        maker_probability=float(exch_cfg.get("maker_probability", 0.0)),
                    )
                    if exch_cfg.get("force_limit"):
                        bt_kwargs["force_limit"] = True
                except Exception:
                    pass

            bt = Backtester(**bt_kwargs)
            cls = get_strategy(config.get("strategy_id", "ma_cross"))
            strategy = cls()
            strategy.init({})
            bt.set_strategy(strategy)

            # Load data so optimizer can run backtests
            data = await self._load_data(config)
            if data is None or data.empty:
                _optimize_tasks[task_id] = {
                    "status": "error",
                    "error": "No data available for optimization",
                }
                return
            bt.set_data(data)

            param_space = {}
            raw_ranges = []
            for p in config.get("param_space", []):
                param_space[p["name"]] = {
                    "type": "range",
                    "min": p["min"],
                    "max": p["max"],
                    "step": p.get("step", 1),
                }
                raw_ranges.append(p)

            opt = Optimizer(bt, metric="sharpe_ratio")
            if config.get("algorithm") == "bayesian":
                results = opt.bayesian_optimization(param_space, n_iterations=config.get("max_trials", 30))
            elif config.get("algorithm") == "genetic":
                results = opt.genetic_algorithm(param_space)
            else:
                results = opt.grid_search(param_space)

            # Build 2D grid matrix only when exactly 2 range params
            grid = None
            if len(raw_ranges) == 2:
                px, py = raw_ranges[0]["name"], raw_ranges[1]["name"]
                import numpy as np
                x_vals = list(np.arange(raw_ranges[0]["min"], raw_ranges[0]["max"] + raw_ranges[0]["step"], raw_ranges[0]["step"]))
                y_vals = list(np.arange(raw_ranges[1]["min"], raw_ranges[1]["max"] + raw_ranges[1]["step"], raw_ranges[1]["step"]))
                score_map = {}
                for r in results:
                    score_map[(r["params"].get(px), r["params"].get(py))] = r["score"]
                matrix = []
                for yv in y_vals:
                    row = []
                    for xv in x_vals:
                        row.append(score_map.get((xv, yv), None))
                    matrix.append(row)
                grid = {
                    "param_x": px,
                    "param_y": py,
                    "x_values": [float(v) for v in x_vals],
                    "y_values": [float(v) for v in y_vals],
                    "scores": matrix,
                }

            _optimize_tasks[task_id] = {
                "status": "completed",
                "best_params": results[0]["params"] if results else {},
                "best_score": results[0]["score"] if results else 0.0,
                "trials": [{"params": r["params"], "score": r["score"]} for r in results[:10]],
                "grid": grid,
            }
        except Exception as e:
            _optimize_tasks[task_id] = {"status": "error", "error": str(e)}

    def get_results(self, task_id: str) -> dict:
        task = _optimize_tasks.get(task_id, {})
        return {"task_id": task_id, "status": task.get("status", "error"), **task}