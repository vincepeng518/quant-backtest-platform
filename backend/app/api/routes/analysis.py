from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.schemas import AnalysisResultOut
from app.services.analysis_service import AnalysisService

router = APIRouter(prefix="/api/analysis", tags=["analysis"])
svc = AnalysisService()


@router.post("/walk-forward", status_code=202)
async def run_walk_forward(config: dict):
    return await svc.run_walk_forward(config)


@router.post("/monte-carlo", status_code=202)
async def run_monte_carlo(config: dict):
    return await svc.run_monte_carlo(config)


@router.get("/results/{task_id}")
async def get_results(task_id: str):
    r = svc.get_results(task_id)
    if r.get("status") == "error":
        raise HTTPException(status_code=404, detail=r.get("error", "Not found"))
    return AnalysisResultOut(**r)