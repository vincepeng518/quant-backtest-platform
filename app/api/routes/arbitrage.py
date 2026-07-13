from __future__ import annotations

import pandas as pd

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.arbitrage import ArbitrageEngine, ArbConfig
from engine.exchange import ExchangeModel
from engine.funding import FundingModel, FundingSchedule

router = APIRouter(prefix="/api/arbitrage", tags=["arbitrage"])


class ArbExchangeConfig(BaseModel):
    enabled: bool = False
    maker_fee: float = 0.0002
    taker_fee: float = 0.0005
    maker_probability: float = 0.0
    latency_bars: int = 0
    book_base_slippage: float = 0.0005


class ArbRunRequest(BaseModel):
    long_symbol: str = "BTC/USDT"
    long_source: str = "bingx"
    short_symbol: str = "BTC/USDT"
    short_source: str = "binance"
    timeframe: str = "1h"
    start_date: str = ""
    end_date: str = ""
    initial_capital: float = 100_000.0
    allocation_pct: float = 0.5
    leverage: float = 1.0
    entry_threshold: float = 0.003
    exit_threshold: float = 0.001
    funding_enabled: bool = False
    funding_interval_hours: int = 8
    funding_rate: float = 0.0001
    long_exchange: ArbExchangeConfig = Field(default_factory=ArbExchangeConfig)
    short_exchange: ArbExchangeConfig = Field(default_factory=ArbExchangeConfig)
    basis_simulation: bool = False
    basis_amp: float = 0.01
    basis_window: int = 40


def _build_exchange(cfg: ArbExchangeConfig) -> ExchangeModel | None:
    if not cfg.enabled:
        return None
    return ExchangeModel(
        maker_fee=cfg.maker_fee,
        taker_fee=cfg.taker_fee,
        latency_bars=cfg.latency_bars,
        book_base_slippage=cfg.book_base_slippage,
        maker_probability=cfg.maker_probability,
    )


@router.post("/run")
async def run_arbitrage(req: ArbRunRequest):
    from app.services.data_service import DataService

    ds = DataService()
    long_data = await ds.get_ohlcv(
        symbol=req.long_symbol, timeframe=req.timeframe,
        start_date=req.start_date, end_date=req.end_date, source=req.long_source,
    )
    short_data = await ds.get_ohlcv(
        symbol=req.short_symbol, timeframe=req.timeframe,
        start_date=req.start_date, end_date=req.end_date, source=req.short_source,
    )
    if long_data.empty or short_data.empty:
        raise HTTPException(status_code=400, detail="No data for one or both venues")

    if req.basis_simulation:
        # Inject a transient venue dislocation into the short venue so the arb
        # engine has a tradable basis to capture (simulates funding/liquidity gaps).
        n = len(short_data)
        ramp = pd.Series(0.0, index=short_data.index)
        w = max(1, min(req.basis_window, n))
        mid = n // 2
        start = max(0, mid - w // 2)
        end = min(n, start + w)
        ramp.iloc[start:end] = req.basis_amp
        for col in ("open", "high", "low", "close"):
            short_data = short_data.copy()
            short_data[col] = short_data[col] * (1 + ramp)

    funding = None
    if req.funding_enabled:
        funding = FundingModel(
            schedule=FundingSchedule(interval_hours=req.funding_interval_hours),
            default_rate=req.funding_rate,
        )

    cfg = ArbConfig(
        initial_capital=req.initial_capital,
        allocation_pct=req.allocation_pct,
        leverage=req.leverage,
        entry_threshold=req.entry_threshold,
        exit_threshold=req.exit_threshold,
        funding=funding,
        long_exchange=_build_exchange(req.long_exchange),
        short_exchange=_build_exchange(req.short_exchange),
    )
    res = ArbitrageEngine(cfg).run(long_data, short_data)
    return {
        "status": "completed",
        "metrics": {
            "total_trades": res.total_trades,
            "win_rate": res.win_rate,
            "total_return_pct": res.total_return_pct,
            "total_pnl": res.total_pnl,
            "max_drawdown": res.max_drawdown,
            "sharpe_ratio": res.sharpe_ratio,
            "profit_factor": res.profit_factor,
            "avg_trade": res.avg_trade,
        },
        "equity_curve": res.equity_curve,
        "trades": [
            {
                "entry_time": str(t.entry_time),
                "entry_price": t.entry_price,
                "exit_time": str(t.exit_time) if t.exit_time else None,
                "exit_price": t.exit_price,
                "size": t.size,
                "pnl": t.pnl,
                "pnl_pct": t.pnl_pct,
                "funding_paid": t.funding_paid,
            }
            for t in res.trades
        ],
    }
