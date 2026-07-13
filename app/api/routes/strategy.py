from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.schemas import StrategyTemplate, UserStrategyUpload, UserStrategyMeta
from app.services import strategy_service as ss

router = APIRouter(prefix="/api/strategy", tags=["strategy"])


@router.get("/templates", response_model=list[StrategyTemplate])
async def get_templates():
    out = []
    for name, cls in ss._registry.items():
        try:
            inst = cls()
            params = inst.get_params_space() or {}
        except Exception:
            params = {}
        out.append(StrategyTemplate(
            id=name,
            name=cls.description or name,
            description=cls.__doc__ or "",
            category=getattr(cls, "category", ""),
            params=[{"name": k, **v} for k, v in params.items()],
        ))
    return out


@router.post("/upload", status_code=201)
async def upload(payload: UserStrategyUpload):
    r = ss.upload_strategy(payload.model_dump())
    if "error" in r and r.get("code") == "SYNTAX_ERROR":
        raise HTTPException(status_code=400, detail=r["error"])
    return r


@router.get("/user", response_model=list[UserStrategyMeta])
async def list_user():
    return ss.list_user_strategies()


@router.get("/user/{sid}")
async def get_user(sid: str):
    r = ss.get_user_strategy(sid)
    if "error" in r:
        raise HTTPException(status_code=404, detail=r["error"])
    return r


@router.put("/user/{sid}")
async def update_user(sid: str, payload: UserStrategyUpload):
    r = ss.update_strategy(sid, payload.model_dump())
    if "error" in r and r.get("code") == "SYNTAX_ERROR":
        raise HTTPException(status_code=400, detail=r["error"])
    if "error" in r:
        raise HTTPException(status_code=404, detail=r["error"])
    return r


@router.delete("/user/{sid}")
async def delete_user(sid: str):
    r = ss.delete_strategy(sid)
    if "error" in r:
        raise HTTPException(status_code=404, detail=r["error"])
    return r
