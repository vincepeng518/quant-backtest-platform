from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.services.research_service import ResearchService

router = APIRouter(prefix="/research", tags=["research"])
_svc = ResearchService()


@router.post("/run", status_code=202)
async def run_research(payload: dict[str, Any]):
    rtype = payload.get("type", "market")
    if rtype == "signal":
        return await _svc.run_signal_research(payload)
    return await _svc.run_market_research(payload)


@router.get("/results/{task_id}")
async def get_results(task_id: str):
    return _svc.get_results(task_id)
