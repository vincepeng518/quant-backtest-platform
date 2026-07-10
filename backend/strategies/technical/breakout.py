from __future__ import annotations

from typing import Any, Optional

from strategies.base import Bar, Signal, StrategyBase


class BreakoutStrategy(StrategyBase):
    """突破策略：價格突破 N 根 K 線最高價買入，跌破最低價賣出。"""

    name = "breakout"
    description = "突破策略"
    category = "trend"

    def init(self, params: dict[str, Any]) -> None:
        super().init(params)
        self.lookback = int(params.get("lookback_period", 20))
        self.risk_percent = float(params.get("risk_percent", 2.0))
        self.highs: list[float] = []
        self.lows: list[float] = []

    def next(self, bar: Bar) -> Optional[Signal]:
        self.highs.append(bar.high)
        self.lows.append(bar.low)
        if len(self.highs) < self.lookback:
            return None

        recent_high = max(self.highs[-self.lookback : -1])
        recent_low = min(self.lows[-self.lookback : -1])

        if bar.close > recent_high and (self.position is None or self.position.size == 0):
            return Signal(action="buy", price=bar.close, stop_loss=bar.close * (1 - self.risk_percent / 100))
        if bar.close < recent_low and self.position is not None:
            return Signal(action="close")

        return None

    def get_params_space(self) -> dict[str, Any]:
        return {
            "lookback_period": {"type": "range", "min": 10, "max": 100, "step": 1},
            "risk_percent": {"type": "range", "min": 0.5, "max": 5.0, "step": 0.25},
        }

    def warmup_period(self) -> int:
        return self.lookback

    def get_params(self) -> dict[str, Any]:
        return {"lookback_period": self.lookback, "risk_percent": self.risk_percent}