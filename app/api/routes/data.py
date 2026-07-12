from __future__ import annotations

from fastapi import APIRouter

from app.models.schemas import OHLCVPoint, SymbolInfo
from app.services.data_service import DataService

router = APIRouter(prefix="/api/data", tags=["data"])
ds = DataService()


@router.post("/import")
async def import_csv():
    return {"symbol_id": "custom", "rows_imported": 0}


@router.get("/symbols", response_model=list[SymbolInfo])
async def get_symbols():
    return await ds.get_symbols()


@router.get("/ohlcv", response_model=list[OHLCVPoint])
async def get_ohlcv(symbol: str, timeframe: str = "1h"):
    df = await ds.get_ohlcv(symbol, timeframe)
    if df.empty:
        return []
    return df.to_dict(orient="records")