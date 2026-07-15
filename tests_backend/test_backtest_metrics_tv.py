from __future__ import annotations

import pandas as pd
import pytest

from engine.backtester import Backtester, BacktestResult, Trade


def _make_result(trades: list[Trade]) -> BacktestResult:
    """Build a BacktestResult via the real _calculate_metrics code path.

    This is the same pipeline the engine runs after a backtest, so it
    verifies that largest_loss / largest_loss_pct / net_profit (total_pnl)
    are computed and emitted correctly.
    """
    equity = [100_000.0] * (len(trades) + 1)
    dd = [0.0] * (len(trades) + 1)
    bh = list(equity)
    ts = [pd.Timestamp("2024-01-01")] * (len(trades) + 1)
    bt = Backtester(initial_capital=100_000)
    return bt._calculate_metrics(trades, equity, dd, buy_hold_curve=bh, timestamps=ts)


def test_largest_loss_and_net_profit():
    trades = [
        Trade(
            entry_time=pd.Timestamp("2024-01-01"),
            entry_price=100.0,
            size=1.0,
            exit_time=pd.Timestamp("2024-01-02"),
            exit_price=110.0,
            pnl=1000.0,
            pnl_pct=1.0,
            direction="long",
            exit_reason="signal",
            holding_bars=1,
        ),
        Trade(
            entry_time=pd.Timestamp("2024-01-02"),
            entry_price=100.0,
            size=1.0,
            exit_time=pd.Timestamp("2024-01-03"),
            exit_price=95.0,
            pnl=-500.0,
            pnl_pct=-0.5,
            direction="long",
            exit_reason="signal",
            holding_bars=1,
        ),
        Trade(
            entry_time=pd.Timestamp("2024-01-03"),
            entry_price=100.0,
            size=1.0,
            exit_time=pd.Timestamp("2024-01-04"),
            exit_price=90.0,
            pnl=-2000.0,
            pnl_pct=-2.0,
            direction="short",
            exit_reason="liquidation",
            holding_bars=1,
        ),
    ]
    result = _make_result(trades)

    # net profit == total pnl (sum of all trade pnls)
    assert result.total_pnl == pytest.approx(1000.0 - 500.0 - 2000.0)
    assert result.total_pnl == pytest.approx(-1500.0)

    # largest loss in $ is the most negative single-trade pnl
    assert result.largest_loss == pytest.approx(-2000.0)

    # largest loss in % is the most negative single-trade pnl_pct
    assert result.largest_loss_pct == pytest.approx(-2.0)


def test_no_losers_yields_zero_largest_loss():
    trades = [
        Trade(
            entry_time=pd.Timestamp("2024-01-01"),
            entry_price=100.0,
            size=1.0,
            exit_time=pd.Timestamp("2024-01-02"),
            exit_price=110.0,
            pnl=500.0,
            pnl_pct=0.5,
            direction="long",
            exit_reason="signal",
            holding_bars=1,
        ),
    ]
    result = _make_result(trades)
    assert result.total_pnl == pytest.approx(500.0)
    assert result.largest_loss == 0.0
    assert result.largest_loss_pct == 0.0


def test_empty_trades_yields_zero_largest_loss():
    result = _make_result([])
    assert result.total_trades == 0
    assert result.total_pnl == 0.0
    assert result.largest_loss == 0.0
    assert result.largest_loss_pct == 0.0


def test_trade_fields_populated():
    t = Trade(
        entry_time=pd.Timestamp("2024-01-01"),
        entry_price=100.0,
        size=1.0,
        direction="short",
        exit_reason="end",
        holding_bars=42,
    )
    assert t.direction == "short"
    assert t.exit_reason == "end"
    assert t.holding_bars == 42


def test_trade_defaults():
    t = Trade(entry_time=pd.Timestamp("2024-01-01"), entry_price=100.0, size=1.0)
    assert t.direction == "long"
    assert t.exit_reason == ""
    assert t.holding_bars == 0


def test_position_status_from_trades():
    """Each trade yields an entry (direction) and exit (flat) segment.

    Segments must be sorted by time and carry correct states.
    """
    trades = [
        Trade(
            entry_time=pd.Timestamp("2024-01-01"),
            entry_price=100.0,
            size=1.0,
            exit_time=pd.Timestamp("2024-01-02"),
            exit_price=110.0,
            pnl=1000.0,
            direction="long",
        ),
        Trade(
            entry_time=pd.Timestamp("2024-01-02"),
            entry_price=110.0,
            size=1.0,
            exit_time=pd.Timestamp("2024-01-03"),
            exit_price=95.0,
            pnl=-500.0,
            direction="short",
        ),
    ]
    result = _make_result(trades)
    ps = result.position_status

    # 2 trades -> 2 entry + 2 exit = 4 segments
    assert len(ps) == 4

    # sorted ascending by time (unix seconds)
    times = [seg["time"] for seg in ps]
    assert times == sorted(times)

    # states in chronological order: long, flat (overlap handled by sort),
    # short, flat
    states = [seg["state"] for seg in ps]
    assert states[0] == "long"
    assert "flat" in states
    assert "short" in states
    assert all(s in ("long", "short", "flat") for s in states)


def test_position_status_no_trades_is_empty():
    result = _make_result([])
    assert result.position_status == []


def test_position_status_skips_missing_exit_time():
    """A trade with no exit_time omits the 'flat' segment."""
    trades = [
        Trade(
            entry_time=pd.Timestamp("2024-01-01"),
            entry_price=100.0,
            size=1.0,
            exit_time=None,
            direction="long",
        ),
    ]
    result = _make_result(trades)
    ps = result.position_status
    assert len(ps) == 1
    assert ps[0]["state"] == "long"
    assert ps[0]["time"] == int(pd.Timestamp("2024-01-01").timestamp())
