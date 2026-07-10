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

    def next(self, bar: Bar) -> Optional[Signal]:
        self.prices.append(bar.close)
        if len(self.prices) < self.slow_period:
            return None

        fast_ma = sum(self.prices[-self.fast_period :]) / self.fast_period
        slow_ma = sum(self.prices[-self.slow_period :]) / self.slow_period

        # Need previous values to detect crossover
        prev_fast = sum(self.prices[-self.fast_period - 1 : -1]) / self.fast_period
        prev_slow = sum(self.prices[-self.slow_period - 1 : -1]) / self.slow_period

        # Golden cross
        if prev_fast <= prev_slow and fast_ma > slow_ma:
            if self.direction in ("long", "both") and (self.position is None or self.position.size == 0):
                return Signal(action="buy", price=bar.close)
        # Death cross
        elif prev_fast >= prev_slow and fast_ma < slow_ma:
            if self.position is not None and self.position.size != 0:
                return Signal(action="close")
            if self.direction in ("short", "both"):
                return Signal(action="sell", price=bar.close)

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
        return {"fast_period": self.fast_period, "slow_period": self.slow_period, "trade_direction": self.direction}