"""SL/TP (OCO attached orders) tests for both the bar-level Backtester and
the tick-level ReplayBacktester.

The Signal dataclass carries stop_loss / take_profit as ABSOLUTE PRICES
(e.g. entry - atr*mult). This suite verifies:
  1. stop-loss closes the trade at the SL level, reason='stop_loss'
  2. take-profit closes at the TP level, reason='take_profit'
  3. OCO: when both SL & TP are attached, ONE fills and the sibling is dead —
     the position can't be closed twice, and the other level never fires later.
  4. Existing behavior (no SL/TP) is unchanged.
"""
from __future__ import annotations

import pandas as pd
import pytest

from engine.backtester import Backtester
from engine.replay import ReplayBacktester
from strategies.base import Bar, Signal, StrategyBase
from tests_backend.conftest import make_ohlcv


class _SLTPStrategy(StrategyBase):
    """Emits a single 'buy' at bar 0 (after warmup), then stays flat.

    Params:
      sl: absolute stop-loss price for the entry signal
      tp: absolute take-profit price for the entry signal
    """
    name = "sltp_test"

    def init(self, params):
        self.params = params
        self._fired = False

    def next(self, bar):
        if not self._fired:
            self._fired = True
            return Signal(
                action="buy",
                price=bar.close,
                stop_loss=self.params.get("sl"),
                take_profit=self.params.get("tp"),
            )
        return None


def _run(engine, df: pd.DataFrame, sl=None, tp=None):
    s = _SLTPStrategy()
    s.init({"sl": sl, "tp": tp})
    engine.set_strategy(s)
    engine.set_data(df)
    return engine.run()


# ── fixture: a monotonic downtrend after bar 0 → long gets stopped out ──
def _downtrend_df():
    closes = [100.0, 100.5, 100.2, 99.5, 98.0, 96.0, 94.0, 92.0, 90.0, 88.0]
    rows = []
    for i, c in enumerate(closes):
        rows.append({
            "timestamp": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i),
            "open": c, "high": c + 1.0, "low": c - 1.0, "close": c,
            "volume": 1000,
        })
    return pd.DataFrame(rows)


# ── fixture: monotonic uptrend → long take-profit fires ──
def _uptrend_df():
    closes = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 110.0]
    rows = []
    for i, c in enumerate(closes):
        rows.append({
            "timestamp": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i),
            "open": c, "high": c + 1.0, "low": c - 1.0, "close": c,
            "volume": 1000,
        })
    return pd.DataFrame(rows)


# ── fixture: SL below entry, TP above entry; price first dips (SL zone) then
#    rips up past TP. With OCO the SL must win (it fires first on the dip) and
#    TP must NOT fire afterwards — proving the sibling was cancelled.
def _dip_then_rip_df():
    closes = [100.0, 98.0, 96.0, 95.0, 99.0, 103.0, 106.0, 109.0, 112.0, 115.0]
    rows = []
    for i, c in enumerate(closes):
        rows.append({
            "timestamp": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i),
            "open": c, "high": c + 1.5, "low": c - 1.5, "close": c,
            "volume": 1000,
        })
    return pd.DataFrame(rows)


ENGINE_FACTORIES = [
    pytest.param(lambda: Backtester(initial_capital=100_000, commission=0.0, slippage=0.0), id="backtester"),
    pytest.param(lambda: ReplayBacktester(initial_capital=100_000, commission=0.0, slippage=0.0, ticks_per_bar=20, tick_seed=42), id="replay"),
]


@pytest.mark.parametrize("factory", ENGINE_FACTORIES)
def test_stop_loss_fires(factory):
    res = _run(factory(), _downtrend_df(), sl=97.0)
    assert res.total_trades == 1
    t = res.trades[0]
    assert t.exit_reason == "stop_loss"
    assert t.exit_price <= 97.0 + 1e-9  # slippage=0 → fill exactly at SL


@pytest.mark.parametrize("factory", ENGINE_FACTORIES)
def test_take_profit_fires(factory):
    res = _run(factory(), _uptrend_df(), tp=106.0)
    assert res.total_trades == 1
    t = res.trades[0]
    assert t.exit_reason == "take_profit"
    assert t.exit_price >= 106.0 - 1e-9


@pytest.mark.parametrize("factory", ENGINE_FACTORIES)
def test_oco_sibling_cancelled(factory):
    """SL 96.0 (dip reaches 95.0) + TP 110.0 (rip reaches 115.0). The dip comes
    first, so the SL fills; afterwards price blasts past TP but the position is
    already flat — total_trades must be exactly 1 and reason must be stop_loss.
    """
    res = _run(factory(), _dip_then_rip_df(), sl=96.0, tp=110.0)
    assert res.total_trades == 1, f"OCO double-close: {res.total_trades} trades"
    assert res.trades[0].exit_reason == "stop_loss"


@pytest.mark.parametrize("factory", ENGINE_FACTORIES)
def test_no_sltp_behavior_unchanged(factory):
    """No SL/TP attached → no OCO orders are placed, position simply stays
    open until data end (no end-of-data flatten in this engine), and no
    stop_loss/take_profit trade records appear."""
    res = _run(factory(), _uptrend_df())
    assert res.total_trades == 0
    assert all(t.exit_reason not in ("stop_loss", "take_profit") for t in res.trades)
