from __future__ import annotations

import pandas as pd
from fastapi import APIRouter

from app.models.schemas import OHLCVPoint, SymbolInfo
from app.services.data_service import DataService

router = APIRouter(prefix="/api/data", tags=["data"])
ds = DataService()


def _to_unix_ms(ts) -> "pd.Series":
    return ts.astype("int64") // 10**6  # nanoseconds -> milliseconds


@router.post("/import")
async def import_csv():
    return {"symbol_id": "custom", "rows_imported": 0}


@router.get("/symbols", response_model=list[SymbolInfo])
async def get_symbols():
    return await ds.get_symbols()


@router.get("/ohlcv", response_model=list[OHLCVPoint])
async def get_ohlcv(symbol: str, timeframe: str = "1h", source: str = "bingx", start_date: str = "", end_date: str = ""):
    df = await ds.get_ohlcv(symbol, timeframe, start_date, end_date, source=source)
    if df is None or df.empty:
        return []
    # coerce timestamp to unix milliseconds (int) so it preserves sub-second precision
    out = df.copy()
    if str(out["timestamp"].dtype).startswith("datetime"):
        out["timestamp"] = _to_unix_ms(out["timestamp"])
    return out.to_dict(orient="records")