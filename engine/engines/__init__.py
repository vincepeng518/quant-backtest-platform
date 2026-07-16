from __future__ import annotations

from typing import Any, Optional

from engine.engines.base import MarketEngine
from engine.engines.crypto import CryptoEngine
from engine.engines.equity import EquityEngine
from engine.engines.forex import ForexEngine
from engine.execution import ExecutionConfig


def _exec_cfg(config: dict) -> Optional[ExecutionConfig]:
    """Build ExecutionConfig from config['execution'] if present (else None = legacy)."""
    ec = config.get("execution")
    if not ec:
        return None
    return ExecutionConfig(
        slippage_ticks=ec.get("slippage_ticks", 0.0),
        entry_slippage_pct=ec.get("entry_slippage_pct", 0.0),
        exit_slippage_pct=ec.get("exit_slippage_pct", 0.0),
        prob_fill_on_limit=ec.get("prob_fill_on_limit", 1.0),
        latency_ms=ec.get("latency_ms", 0.0),
        min_synthetic_book_size=ec.get("min_synthetic_book_size", 0.0),
        tick_size=ec.get("tick_size", config.get("tick_size", 0.01)),
    )


def build_market_engine(market: str, config: dict) -> Optional[MarketEngine]:
    """Factory: build the appropriate MarketEngine from a backtest config.

    Args:
        market: 'crypto' | 'equity' | 'forex' (anything else -> None = legacy path)
        config: the full backtest config dict (reads funding/perpetual/exchange/execution sub-configs)
    """
    exec_cfg = _exec_cfg(config)
    if market == "crypto":
        funding_cfg = config.get("funding") or {}
        perp_cfg = config.get("perpetual") or {}
        exch_cfg = config.get("exchange") or {}
        funding = None
        perp = None
        if funding_cfg.get("enabled"):
            try:
                from engine.funding import FundingModel, FundingSchedule
                funding = FundingModel(
                    schedule=FundingSchedule(interval_hours=funding_cfg.get("interval_hours", 8)),
                    default_rate=funding_cfg.get("default_rate", 0.0001),
                )
            except Exception:
                funding = None
        if perp_cfg.get("enabled"):
            try:
                from engine.perpetual import PerpSimulator
                perp = PerpSimulator(
                    maintenance_margin_rate=perp_cfg.get("maintenance_margin_rate", 0.005),
                    use_tiered=True,
                )
            except Exception:
                perp = None
        maker = exch_cfg.get("maker_fee", 0.0002)
        taker = exch_cfg.get("taker_fee", 0.0005)
        slip = config.get("slippage", 0.0005)
        lev = float(perp_cfg.get("leverage", config.get("leverage", 1.0)))
        return CryptoEngine(maker_rate=maker, taker_rate=taker, slippage=slip, funding=funding, perp=perp, leverage=lev, exec_cfg=exec_cfg)

    if market == "equity":
        eq = config.get("equity") or {}
        return EquityEngine(
            commission_pct=eq.get("commission_pct", 0.0005),
            commission_min=eq.get("commission_min", 1.0),
            slippage=eq.get("slippage", 0.0002),
            t1_delay=eq.get("t1_delay", True),
            exec_cfg=exec_cfg,
        )

    if market == "forex":
        fx = config.get("forex") or {}
        return ForexEngine(
            spread_pips=fx.get("spread_pips", 0.0001),
            contract_size=fx.get("contract_size", 100_000),
            leverage=fx.get("leverage", 30.0),
            exec_cfg=exec_cfg,
        )

    return None
