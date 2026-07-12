from __future__ import annotations

from typing import Any, Optional

from strategies.base import Bar, Position, Signal, StrategyBase


class MovingAverageCrossStrategy(StrategyBase):
    """均線交叉：快線上穿慢線買入，下穿賣出。"""

    name = "ma_cross"
    description = "均線交叉策略"
    category = "trend"

    def init(self, params: dict[str, Any]) -> None:
        super().init(params)
        self.fast_period: int = int(params.get("fast_period", 20))
        self.slow_period: int = int(params.get("slow_period", 50))
        self.direction = params.get("trade_direction", "both")
        self.prices: list[float] = []
        # Internal position state (strategy owns its own book)
        self._pos: int = 0  # -1 short, 0 flat, +1 long

    def next(self, bar: Bar) -> Optional[Signal]:
        self.prices.append(bar.close)
        if len(self.prices) < self.slow_period:
            return None

        fast_ma = sum(self.prices[-self.fast_period :]) / self.fast_period
        slow_ma = sum(self.prices[-self.slow_period :]) / self.slow_period

        # Previous MAs for crossover detection
        prev_fast = sum(self.prices[-self.fast_period - 1 : -1]) / self.fast_period
        prev_slow = sum(self.prices[-self.slow_period - 1 : -1]) / self.slow_period

        golden = prev_fast <= prev_slow and fast_ma > slow_ma
        death = prev_fast >= prev_slow and fast_ma < slow_ma

        # Golden cross → go long (if flat / allowed)
        if golden:
            if self._pos <= 0 and self.direction in ("long", "both"):
                self._pos = 1
                return Signal(action="buy", price=bar.close)
            if self._pos >= 0 and self.direction in ("short", "both"):
                self._pos = -1
                return Signal(action="sell", price=bar.close)

        # Death cross → flatten / reverse
        if death:
            if self._pos > 0:
                self._pos = 0
                return Signal(action="close", price=bar.close)
            if self._pos < 0 and self.direction in ("short", "both"):
                self._pos = 0
                return Signal(action="close", price=bar.close)
        return None

    def get_params_space(self) -> dict[str, Any]:
        return {
            "fast_period": {"type": "range", "min": 5, "max": 50, "step": 1},
            "slow_period": {"type": "range", "min": 20, "max": 200, "step": 1},
            "trade_direction": {"type": "choice", "values": ["long", "short", "both"]},
        }

    def warmup_period(self) -> int:
        return self.slow_period

    def get_params(self) -> dict[str, Any]:
        return {
            "fast_period": self.fast_period,
            "slow_period": self.slow_period,
            "trade_direction": self.direction,
        }
