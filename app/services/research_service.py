from __future__ import annotations

import asyncio
from typing import Any

from app.services.data_service import DataService, _analysis_tasks, create_task_id
from engine.research import market_profile, signal_profile
from app.services.strategy_service import get_strategy

# Default to offline/test data so Research works without live exchange access.
_DEFAULT_SOURCE = "test"


class ResearchService:
    def __init__(self) -> None:
        self.data_service = DataService()

    async def run_market_research(self, config: dict[str, Any]) -> dict:
        task_id = create_task_id()
        _analysis_tasks[task_id] = {"status": "running"}
        asyncio.create_task(self._exec_market(task_id, config))
        return {"task_id": task_id, "status": "running"}

    async def run_signal_research(self, config: dict[str, Any]) -> dict:
        task_id = create_task_id()
        _analysis_tasks[task_id] = {"status": "running"}
        asyncio.create_task(self._exec_signal(task_id, config))
        return {"task_id": task_id, "status": "running"}

    async def _exec_market(self, task_id: str, config: dict) -> None:
        try:
            symbol = config.get("symbol", "BTC/USDT")
            timeframe = config.get("timeframe", "1h")
            start_date = config.get("start_date", "")
            end_date = config.get("end_date", "")
            source = config.get("source", _DEFAULT_SOURCE)
            data = await self.data_service.get_ohlcv(
                symbol, timeframe, start_date, end_date, source
            )
            if data is None or len(data) == 0:
                _analysis_tasks[task_id] = {"status": "error", "error": "No data available"}
                return
            # Optional benchmark (correlation vs BTC/USDT) for non-BTC symbols.
            bench = None
            if symbol.upper() != "BTC/USDT":
                bench = await self.data_service.get_ohlcv(
                    "BTC/USDT", timeframe, start_date, end_date, source
                )
            result = market_profile(data, bench)
            _analysis_tasks[task_id] = {"status": "completed", "result": result}
        except Exception as e:  # noqa: BLE001
            _analysis_tasks[task_id] = {"status": "error", "error": str(e)}

    async def _exec_signal(self, task_id: str, config: dict) -> None:
        try:
            symbol = config.get("symbol", "BTC/USDT")
            timeframe = config.get("timeframe", "1h")
            start_date = config.get("start_date", "")
            end_date = config.get("end_date", "")
            source = config.get("source", _DEFAULT_SOURCE)
            data = await self.data_service.get_ohlcv(
                symbol, timeframe, start_date, end_date, source
            )
            if data is None or len(data) == 0:
                _analysis_tasks[task_id] = {"status": "error", "error": "No data available"}
                return
            cls = get_strategy(config.get("strategy_id", "ma_cross"))
            result = signal_profile(data, cls, config.get("params", {}))
            _analysis_tasks[task_id] = {"status": "completed", "result": result}
        except Exception as e:  # noqa: BLE001
            _analysis_tasks[task_id] = {"status": "error", "error": str(e)}

    def get_results(self, task_id: str) -> dict:
        task = _analysis_tasks.get(task_id, {})
        r = task.get("result", {})
        return {
            "task_id": task_id,
            "status": task.get("status", "error"),
            "summary": r if isinstance(r, dict) else {},
        }
