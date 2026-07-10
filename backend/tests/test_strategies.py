from __future__ import annotations

import pandas as pd
import pytest

from strategies.base import Bar
from strategies.technical.moving_average import MovingAverageCrossStrategy
from strategies.technical.breakout import BreakoutStrategy
from strategies.technical.pairs import PairsTradingStrategy


def _make_bars(closes: list[float]) -> list[Bar]:
    return [Bar(timestamp=pd.Timestamp.now(), open=c, high=c * 1.01, low=c * 0.99, close=c, volume=100) for c in closes]


class TestMovingAverageCross:
    def test_golden_cross(self):
        s = MovingAverageCrossStrategy()
        s.init({"fast_period": 3, "slow_period": 6})

        # Generate uptrend → golden cross
        prices = [10, 10.5, 11, 11.5, 12, 12.5, 13, 13.5, 14, 14.5, 15, 10, 11, 12, 13, 14, 15, 16]
        signals = [s.next(b) for b in _make_bars(prices)]
        buy_signals = [sig for sig in signals if sig and sig.action == "buy"]
        assert len(buy_signals) > 0, "Golden cross should produce a buy signal"


class TestBreakout:
    def test_breakout_high(self):
        s = BreakoutStrategy()
        s.init({"lookback_period": 5, "risk_percent": 2.0})
        prices = [100, 101, 102, 100, 99, 110]
        bars = _make_bars(prices)
        signals = [s.next(b) for b in bars]
        # ponytail: last bar should trigger breakout
        assert any(sig and sig.action == "buy" for sig in signals[-3:]), "Breakout should trigger buy"