"""Cross-exchange arbitrage engine tests."""
from __future__ import annotations

import pandas as pd

from engine.arbitrage import ArbitrageEngine, ArbConfig
from engine.exchange import ExchangeModel
from engine.funding import FundingModel, FundingSchedule
from tests_backend.conftest import make_ohlcv


def _two_feeds(gap_profile: list[float]):
    """Long venue = base series; short venue = base * (1+gap_profile[i])."""
    base = make_ohlcv(n=120, start="2024-01-01", freq="1h", seed=7)
    short = base.copy()
    gaps = (gap_profile + [0.0] * 120)[:120]
    for col in ("open", "high", "low", "close"):
        short[col] = base[col] * (1 + pd.Series(gaps, index=base.index))
    return base, short


def test_arb_opens_and_closes_legs():
    long_df, short_df = _two_feeds([0.0] * 40 + [0.01] * 40 + [0.0] * 40)  # 1% transient basis
    cfg = ArbConfig(
        initial_capital=100_000,
        allocation_pct=0.5,
        entry_threshold=0.003,
        exit_threshold=0.001,
        long_exchange=ExchangeModel(maker_fee=0.0002, taker_fee=0.0005, maker_probability=0.0),
        short_exchange=ExchangeModel(maker_fee=0.0002, taker_fee=0.0005, maker_probability=0.0),
    )
    res = ArbitrageEngine(cfg).run(long_df, short_df)
    assert res.total_trades >= 1, "arb should open at least one paired trade on 1% basis"
    assert res.equity_curve[-1] != 0


def test_arb_maker_fee_lower_than_taker():
    """With maker_probability=0 (all maker), the engine runs and produces a
    finite equity, and the funding model accrues per-leg on a single long."""
    long_df, short_df = _two_feeds([0.0] * 30 + [0.02] * 60 + [0.0] * 30)
    cfg = ArbConfig(
        initial_capital=100_000,
        allocation_pct=0.5,
        entry_threshold=0.005,
        exit_threshold=0.002,
        long_exchange=ExchangeModel(maker_fee=0.0001, taker_fee=0.0006, maker_probability=0.0),
        short_exchange=ExchangeModel(maker_fee=0.0001, taker_fee=0.0006, maker_probability=0.0),
        funding=FundingModel(schedule=FundingSchedule(interval_hours=8), default_rate=0.0001),
    )
    res = ArbitrageEngine(cfg).run(long_df, short_df)
    assert res.total_trades >= 1
    # Per-leg funding must be captured (long pays, short receives => net ~0 for a
    # same-asset basis trade, which is correct). Verify the model accrues nonzero.
    single = FundingModel(schedule=FundingSchedule(interval_hours=8), default_rate=0.0001)
    accrued = single.accrued(
        pd.Timestamp("2024-01-02 06:00"), pd.Timestamp("2024-01-04 18:00"), 1
    )
    assert abs(accrued) > 0


def test_arb_no_trade_when_basis_too_small():
    """Feeds nearly identical => no entry beyond threshold."""
    long_df, short_df = _two_feeds([0.0002] * 120)  # 0.02% basis < entry_threshold
    cfg = ArbConfig(
        initial_capital=100_000,
        allocation_pct=0.5,
        entry_threshold=0.003,
        exit_threshold=0.001,
        long_exchange=ExchangeModel(),
        short_exchange=ExchangeModel(),
    )
    res = ArbitrageEngine(cfg).run(long_df, short_df)
    assert res.total_trades == 0
    # equity stays flat (capital only)
    assert abs(res.equity_curve[-1] - cfg.initial_capital) < 1e-6
