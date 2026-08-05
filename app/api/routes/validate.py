from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.services.data_service import DataService

router = APIRouter(prefix="/api/validate", tags=["validate"])


@router.post("/indicator")
async def validate_indicator(payload: dict[str, Any]) -> dict:
    """Validate our engine's indicator math against reference values.

    Body: { symbol, timeframe, source, name, period, reference: [numbers] }
    reference = values from an external source (TV chart, another lib, etc.)
    We fetch the same OHLCV, compute the indicator, compare bar-by-bar.
    """
    symbol = payload.get("symbol")
    timeframe = payload.get("timeframe", "1h")
    source = payload.get("source", "bingx")
    name = payload.get("name", "sma")
    try:
        period = int(payload.get("period", 14))
    except (TypeError, ValueError):
        raise HTTPException(400, "period must be an integer")
    reference = payload.get("reference")
    if not symbol or not reference:
        raise HTTPException(400, "symbol and reference are required")
    # timeframe / period bounds (mirror BacktestConfig to avoid 500 on bad values)
    import re
    if not re.fullmatch(r"^\d{1,5}[smhdwM]$", str(timeframe)):
        raise HTTPException(422, f"invalid timeframe: {timeframe!r}")
    if period < 1 or period > 100000:
        raise HTTPException(422, f"period out of range: {period}")

    try:
        from engine.indicator_validation import validate
        ds = DataService()
        df = await ds.get_ohlcv(symbol=symbol, timeframe=timeframe, source=source)
        if df is None or len(df) < period:
            raise HTTPException(400, f"not enough data for {symbol}")
        ref_series = __import__("pandas").Series(reference, index=df["close"].index[-len(reference):])
        result = validate(df["close"], name, period, ref_series)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
