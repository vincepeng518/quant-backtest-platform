from __future__ import annotations

import pandas as pd
import pytest

from strategies.base import Bar
from strategies.technical.moving_average import MovingAverageCrossStrategy
from strategies.technical.breakout import BreakoutStrategy
from strategies.technical.pairs import PairsTradingStrategy
from strategies.technical.arbitrage import StatisticalArbitrageStrategy
from tests.conftest import make_bars


class TestMovingAverageCross:
    def test_golden_cross_generates_buy(self):
        """黃金交叉 → buy 信號"""
        s = MovingAverageCrossStrategy()
        s.init({"fast_period": 3, "slow_period": 6, "trade_direction": "both"})
        prices = [10, 10.5, 11, 11.5, 12, 12.5, 13, 13.5, 14, 14.5, 15, 10, 11, 12, 13, 14, 15, 16]
        signals = [sig for b in make_bars(prices) if (sig := s.next(b))]
        buy_signals = [s for s in signals if s.action == "buy"]
        assert len(buy_signals) > 0

    def test_death_cross_generates_sell(self):
        """死亡交叉 → sell 信號"""
        s = MovingAverageCrossStrategy()
        s.init({"fast_period": 3, "slow_period": 6, "trade_direction": "both"})
        # Uptrend then downtrend — fast MA crosses below slow
        prices = list(range(10, 30)) + [28, 26, 24, 22, 20, 18, 16, 14]
        signals = [sig for b in make_bars(prices) if (sig := s.next(b))]
        sell_signals = [s for s in signals if s.action in ("sell", "close")]
        assert len(sell_signals) > 0

    def test_no_signal_before_warmup(self):
        """預熱期內不產生信號"""
        s = MovingAverageCrossStrategy()
        s.init({"fast_period": 10, "slow_period": 20, "trade_direction": "both"})
        bars = make_bars([100] * 15)
        signals = [sig for b in bars if (sig := s.next(b))]
        assert len(signals) == 0

    def test_params_space(self):
        s = MovingAverageCrossStrategy()
        space = s.get_params_space()
        assert "fast_period" in space
        assert space["fast_period"]["type"] == "range"
        assert "slow_period" in space


class TestBreakout:
    def test_upward_breakout_buy(self):
        """向上突破 → buy"""
        s = BreakoutStrategy()
        s.init({"lookback_period": 5, "risk_percent": 2.0})
        prices = [100] * 5 + [115]
        signals = [sig for b in make_bars(prices) if (sig := s.next(b))]
        assert any(s.action == "buy" for s in signals)
        assert signals[-1].stop_loss is not None

    def test_downward_breakout_close(self):
        """向下突破 → close（當 position 非空時）"""
        s = BreakoutStrategy()
        s.init({"lookback_period": 5, "risk_percent": 2.0})
        # Manually set position to simulate being long
        s.position = __import__("strategies.base", fromlist=["Position"]).Position(
            size=1000, entry_price=115, current_price=115
        )
        bars = make_bars([100, 101, 102, 103, 104, 80])
        sig = None
        for b in bars:
            sig = s.next(b)
        assert sig is not None, "Should generate close signal"
        assert sig.action == "close"

    def test_no_signal_during_consolidation(self):
        s = BreakoutStrategy()
        s.init({"lookback_period": 5, "risk_percent": 2.0})
        bars = make_bars([100, 101, 99, 100, 101] * 3)
        signals = [sig for b in bars if (sig := s.next(b))]
        assert len(signals) == 0

    def test_params_space(self):
        s = BreakoutStrategy()
        space = s.get_params_space()
        assert "lookback_period" in space
        assert "risk_percent" in space


class TestPairsTrading:
    def test_zscore_entry(self):
        s = PairsTradingStrategy()
        s.init({"window": 10, "entry_z": 1.5, "exit_z": 0.5})
        prices = [100.0] * 10 + [120.0, 120.0, 120.0, 120.0, 120.0]
        signals = [sig for b in make_bars(prices) if (sig := s.next(b))]
        assert any(s.action == "sell" for s in signals)

    def test_zscore_exit(self):
        s = PairsTradingStrategy()
        s.init({"window": 10, "entry_z": 1.5, "exit_z": 0.5})
        # Spike up then revert to mean
        prices = [100.0] * 10 + [120.0] * 5 + [105.0] * 5
        signals = [sig for b in make_bars(prices) if (sig := s.next(b))]
        # Should have at least a sell or close signal
        assert len(signals) >= 1


class TestStatisticalArbitrage:
    def test_ou_process_triggers(self):
        s = StatisticalArbitrageStrategy()
        s.init({"lookback": 20, "entry_z": 1.0, "exit_z": 0.2})
        prices = [100] * 20 + [120, 121, 122, 123, 124]
        signals = [sig for b in make_bars(prices) if (sig := s.next(b))]
        close_signals = [s for s in signals if s.action == "close"]
        sell_signals = [s for s in signals if s.action == "sell"]
        assert len(sell_signals) > 0 or len(close_signals) > 0