from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

import numpy as np

from strategies.base import Bar, Signal, StrategyBase


class PairsTradingStrategy(StrategyBase):
    """配對交易：基於價差 Z-Score 的均值回歸。"""

    name = "pairs_trading"
    description = "配對交易策略"
    category = "mean_reversion"

    def init(self, params: dict[str, Any]) -> None:
        super().init(params)
        self.window = params.get("window", 100)
        self.entry_z = params.get("entry_z", 2.0)
        self.exit_z = params.get("exit_z", 0.5)
        self.spread: list[float] = []

    def _calc_zscore(self) -> float:
        arr = np.array(self.spread)
        mean, std = np.mean(arr), np.std(arr)
        return (arr[-1] - mean) / std if std > 0 else 0.0

    def next(self, bar: Bar) -> Optional[Signal]:
        self.spread.append(bar.close)
        if len(self.spread) < self.window:
            return None
        z = self._calc_zscore()

        if z > self.entry_z and (self.position is None or self.position.size == 0):
            return Signal(action="sell", price=bar.close, metadata={"z_score": z})
        if z < -self.entry_z and (self.position is None or self.position.size == 0):
            return Signal(action="buy", price=bar.close, metadata={"z_score": z})
        if abs(z) < self.exit_z and self.position is not None:
            return Signal(action="close", metadata={"z_score": z})
        return None

    def warmup_period(self) -> int:
        return self.window

    def get_params(self) -> dict[str, Any]:
        return {"window": self.window, "entry_z": self.entry_z, "exit_z": self.exit_z}

    def get_params_space(self) -> dict[str, Any]:
        return {
            "window": {"type": "range", "min": 30, "max": 300, "step": 5},
            "entry_z": {"type": "range", "min": 1.0, "max": 3.0, "step": 0.1},
            "exit_z": {"type": "range", "min": 0.1, "max": 1.0, "step": 0.1},
        }