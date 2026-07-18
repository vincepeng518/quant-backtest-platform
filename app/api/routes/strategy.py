from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.models.schemas import StrategyTemplate, UserStrategyUpload, UserStrategyMeta
from app.services import strategy_service as ss
from app.core.auth import auth_required
from app.core.sandbox import check_strategy_code

router = APIRouter(prefix="/api/strategy", tags=["strategy"])


class StrategyValidateRequest(BaseModel):
    template_id: str | None = None


@router.post("/validate")
async def validate_strategy(payload: StrategyValidateRequest = StrategyValidateRequest()):
    """Lightweight check that a strategy template exists. Empty body => 200 (alive)."""
    if payload.template_id is None:
        return {"valid": True, "strategies": list(ss._registry.keys())}
    if payload.template_id not in ss._registry:
        raise HTTPException(status_code=404, detail=f"Strategy '{payload.template_id}' not found")
    return {"valid": True, "template_id": payload.template_id}


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
            params=[{"name": k, **(v if isinstance(v, dict) else {"values": v})} for k, v in params.items()],
        ))
    return out


@router.post("/upload", status_code=201)
async def upload(payload: UserStrategyUpload, _: None = Depends(auth_required)):
    ok, err = check_strategy_code(payload.code)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Strategy rejected: {err}")
    r = ss.upload_strategy(payload.model_dump())
    if "error" in r and r.get("code") == "SYNTAX_ERROR":
        raise HTTPException(status_code=400, detail=r["error"])
    return r


@router.get("/user", response_model=list[UserStrategyMeta])
async def list_user(_: None = Depends(auth_required)):
    return ss.list_user_strategies()


@router.get("/user/{sid}")
async def get_user(sid: str, _: None = Depends(auth_required)):
    r = ss.get_user_strategy(sid)
    if "error" in r:
        raise HTTPException(status_code=404, detail=r["error"])
    return r


@router.put("/user/{sid}")
async def update_user(sid: str, payload: UserStrategyUpload, _: None = Depends(auth_required)):
    ok, err = check_strategy_code(payload.code)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Strategy rejected: {err}")
    r = ss.update_strategy(sid, payload.model_dump())
    if "error" in r and r.get("code") == "SYNTAX_ERROR":
        raise HTTPException(status_code=400, detail=r["error"])
    if "error" in r:
        raise HTTPException(status_code=404, detail=r["error"])
    return r


@router.delete("/user/{sid}")
async def delete_user(sid: str, _: None = Depends(auth_required)):
    r = ss.delete_strategy(sid)
    if "error" in r:
        raise HTTPException(status_code=404, detail=r["error"])
    return r
