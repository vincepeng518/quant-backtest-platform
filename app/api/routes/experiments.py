from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.services.experiment_store import (
    list_experiments,
    get_experiment,
    compare_experiments,
)

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


@router.get("")
def get_all(kind: str | None = None) -> dict:
    return {"experiments": list_experiments(kind)}


@router.get("/{eid}")
def get_one(eid: str) -> dict:
    rec = get_experiment(eid)
    if rec is None:
        return {"error": "not found"}
    return rec


@router.post("/compare")
async def compare(payload: dict[str, Any]) -> dict:
    ids = payload.get("ids", [])
    return compare_experiments(ids)
