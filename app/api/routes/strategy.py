from __future__ import annotations

from fastapi import APIRouter

from app.models.schemas import StrategyTemplate
from app.services.strategy_service import list_templates

router = APIRouter(prefix="/api/strategy", tags=["strategy"])


@router.get("/templates", response_model=list[StrategyTemplate])
async def get_templates():
    return list_templates()


@router.post("/validate")
async def validate():
    return {"valid": True, "errors": []}


@router.get("/config")
async def get_config(template_id: str = "ma_cross"):
    return []