from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.schemas import BacktestConfig, BacktestResultOut, TaskStatus
from app.services.backtest_service import BacktestService

router = APIRouter(prefix="/api/backtest", tags=["backtest"])
svc = BacktestService()


@router.post("/run", status_code=202)
async def run_backtest(config: BacktestConfig):
    return await svc.run(config.model_dump())


@router.get("/status/{task_id}")
async def get_status(task_id: str):
    s = svc.get_status(task_id)
    return TaskStatus(**s)


@router.get("/results/{task_id}", response_model=BacktestResultOut)
async def get_results(task_id: str):
    r = svc.get_results(task_id)
    if "error" in r:
        raise HTTPException(status_code=404, detail=r["error"])
    return BacktestResultOut(**r)