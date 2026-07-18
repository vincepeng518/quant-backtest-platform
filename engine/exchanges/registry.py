from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExchangeSpec:
    """Static fee/latency/liquidity profile for an exchange (backtest realism)."""
    name: str
    maker_fee: float
    taker_fee: float
    latency_ms: float          # signal->order latency (avg)
    book_base_slippage: float  # baseline slippage from book depth
    maker_probability: float   # P(limit rests as maker)
    min_tick: float = 0.01     # price tick size
    notes: str = ""


# Multi-exchange registry. Values are realistic public rates (maker/taker).
# Latency is illustrative (colocation vs retail). Tune per your account tier.
EXCHANGE_REGISTRY: dict[str, ExchangeSpec] = {
    "bingx": ExchangeSpec(
        name="BingX", maker_fee=0.0002, taker_fee=0.0005, latency_ms=120.0,
        book_base_slippage=0.0004, maker_probability=0.35, min_tick=0.01,
        notes="Default; NCCO/NCFX/NCSI/NCSK TradFi contracts available",
    ),
    "binance": ExchangeSpec(
        name="Binance", maker_fee=0.0002, taker_fee=0.0004, latency_ms=80.0,
        book_base_slippage=0.0003, maker_probability=0.45, min_tick=0.01,
        notes="Deepest crypto book; lowest taker",
    ),
    "okx": ExchangeSpec(
        name="OKX", maker_fee=0.0002, taker_fee=0.0005, latency_ms=100.0,
        book_base_slippage=0.00035, maker_probability=0.40, min_tick=0.01,
        notes="Good for perp; unified account",
    ),
    "bybit": ExchangeSpec(
        name="Bybit", maker_fee=0.0001, taker_fee=0.0006, latency_ms=110.0,
        book_base_slippage=0.0004, maker_probability=0.30, min_tick=0.01,
        notes="Low maker rebate",
    ),
}


def get_exchange_spec(name: str) -> Optional[ExchangeSpec]:
    return EXCHANGE_REGISTRY.get(name.lower())


def list_exchanges() -> list[dict]:
    return [
        {
            "id": k,
            "name": v.name,
            "maker_fee": v.maker_fee,
            "taker_fee": v.taker_fee,
            "latency_ms": v.latency_ms,
            "book_base_slippage": v.book_base_slippage,
            "maker_probability": v.maker_probability,
            "notes": v.notes,
        }
        for k, v in EXCHANGE_REGISTRY.items()
    ]
