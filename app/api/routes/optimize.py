from __future__ import annotations

from fastapi import APIRouter

from app.models.schemas import OptimizeConfig, OptimizeResultOut
from app.services.optimize_service import OptimizeService

router = APIRouter(prefix="/api/optimize", tags=["optimize"])
svc = OptimizeService()


@router.post("/run", status_code=202)
async def run_optimize(config: OptimizeConfig):
    from fastapi.responses import JSONResponse
    result = await svc.run(config.model_dump())
    return JSONResponse(content=result, headers={
        "Cache-Control": "no-store, max-age=0, must-revalidate", "Pragma": "no-cache"})


@router.get("/results/{task_id}")
async def get_results(task_id: str):
    from fastapi.responses import JSONResponse
    result = svc.get_results(task_id)
    return JSONResponse(content=result, headers={
        "Cache-Control": "no-store, max-age=0, must-revalidate", "Pragma": "no-cache"})


@router.post("/best-params")
async def apply_best_params():
    return {"applied": True}