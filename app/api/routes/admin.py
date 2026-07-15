from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Depends

from app.core.auth import auth_required
from app.models.schemas import (
    CredentialStatus,
    MonitoredSymbol,
    SiteConfig,
    SiteConfigUpdate,
    TaskHistoryItem,
    UsageStat,
)
from app.services.admin_service import AdminService

router = APIRouter(prefix="/api/admin", tags=["admin"])
svc = AdminService()


@router.get("/overview", response_model=dict)
async def overview(_: None = Depends(auth_required)) -> dict[str, Any]:
    """Single-call bundle for the operator panel (read-only)."""
    return {
        "watchlist": [s.model_dump() for s in svc.get_watchlist()],
        "credentials": [c.model_dump() for c in svc.get_credentials()],
        "task_history": [t.model_dump() for t in svc.get_task_history()],
        "usage": [u.model_dump() for u in svc.get_usage()],
        "config": svc.get_config().model_dump(),
    }


@router.get("/watchlist", response_model=list[MonitoredSymbol])
async def list_watchlist(_: None = Depends(auth_required)) -> list[MonitoredSymbol]:
    return svc.get_watchlist()


@router.post("/watchlist", response_model=MonitoredSymbol, status_code=201)
async def add_watchlist(item: MonitoredSymbol, _: None = Depends(auth_required)) -> MonitoredSymbol:
    try:
        return svc.add_symbol(
            symbol=item.symbol,
            market=item.market,
            exchange=item.exchange,
            description=item.description,
            pinned=item.pinned,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/watchlist", response_model=dict)
async def delete_watchlist(symbol: str, _: None = Depends(auth_required)) -> dict:
    # symbol arrives as a query param (it contains "/", e.g. ETH/USDT, which
    # FastAPI path params refuse to match across a slash).
    ok = svc.remove_symbol(symbol)
    if not ok:
        raise HTTPException(status_code=404, detail="symbol not in watchlist")
    return {"ok": True}


@router.post("/watchlist/pin", response_model=dict)
async def pin_watchlist(symbol: str, _: None = Depends(auth_required)) -> dict:
    ok = svc.toggle_pin(symbol)
    if not ok:
        raise HTTPException(status_code=404, detail="symbol not in watchlist")
    return {"ok": True}


@router.get("/credentials", response_model=list[CredentialStatus])
async def list_credentials(_: None = Depends(auth_required)) -> list[CredentialStatus]:
    return svc.get_credentials()


@router.get("/tasks", response_model=list[TaskHistoryItem])
async def list_tasks(limit: int = 200, _: None = Depends(auth_required)) -> list[TaskHistoryItem]:
    return svc.get_task_history(limit=limit)


@router.get("/usage", response_model=list[UsageStat])
async def usage(_: None = Depends(auth_required)) -> list[UsageStat]:
    return svc.get_usage()


@router.get("/config", response_model=SiteConfig)
async def get_config(_: None = Depends(auth_required)) -> SiteConfig:
    return svc.get_config()


@router.patch("/config", response_model=SiteConfig)
async def patch_config(payload: SiteConfigUpdate, _: None = Depends(auth_required)) -> SiteConfig:
    return svc.update_config(payload)
