from __future__ import annotations

from fastapi import APIRouter, Query

from engine.exchanges.registry import list_exchanges, get_exchange_spec
from engine.exchanges.executor import ExchangeExecutor
from data.providers.bingx_tradfi import BINGX_TRADFI_SYMBOLS

router = APIRouter(prefix="/api/exchanges", tags=["exchanges"])


@router.get("/list")
async def list_all():
    """List all supported exchanges with their fee/latency profile."""
    return {"exchanges": list_exchanges()}


@router.get("/tradfi-symbols")
async def tradfi_symbols():
    """BingX TradFi contract symbols with live status (active/paused/offline/not_exist)."""
    return {
        "symbols": BINGX_TRADFI_SYMBOLS,
        "active_count": sum(1 for s in BINGX_TRADFI_SYMBOLS if s["status"] == "active"),
        "total": len(BINGX_TRADFI_SYMBOLS),
    }


@router.get("/compare-fees")
async def compare_fees(
    symbol: str = Query(..., description="e.g. BTC/USDT or NCCOGOLD2USD-USDT"),
    qty: float = Query(1.0, description="order quantity in base asset"),
    side: str = Query("buy", description="buy | sell"),
    exchanges: str = Query("bingx,binance,okx", description="comma-separated exchange ids"),
):
    """Compare fill cost across multiple exchanges (paper-quoted, no real orders)."""
    ex_list = [e.strip() for e in exchanges.split(",") if e.strip()]
    ex = ExchangeExecutor(exchanges=ex_list, mode="paper")
    import asyncio
    cmp = await ex.compare_fees(symbol, qty, side)
    return {"symbol": symbol, "side": side, "qty": qty, "comparison": cmp}
