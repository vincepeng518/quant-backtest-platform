from __future__ import annotations

from typing import Any, Optional

import numpy as np

from strategies.base import Bar, Signal, StrategyBase


class StatisticalArbitrageStrategy(StrategyBase):
    """統計套利：使用 OU 過程建模價差均值回歸。"""

    name = "stat_arb"
    description = "統計套利策略"
    category = "mean_reversion"

    def init(self, params: dict[str, Any]) -> None:
        super().init(params)
        self.lookback = params.get("lookback", 200)
        self.entry_z = params.get("entry_z", 1.5)
        self.exit_z = params.get("exit_z", 0.3)
        self.prices: list[float] = []

    def _fit_ou(self) -> tuple[float, float]:
        arr = np.array(self.prices)
        spread = arr - np.mean(arr)
        ds = np.diff(spread)
        s_lag = spread[:-1]
        A = np.vstack([s_lag, np.ones_like(s_lag)]).T
        slope, intercept = np.linalg.lstsq(A, ds, rcond=None)[0]
        kappa = -slope
        mu = intercept / kappa if kappa > 0 else np.mean(spread)
        return kappa, mu

    def next(self, bar: Bar) -> Optional[Signal]:
        self.prices.append(bar.close)
        if len(self.prices) < self.lookback:
            return None

        arr = np.array(self.prices)
        mean = np.mean(arr)
        spread = arr - mean
        kappa, mu = self._fit_ou()
        std = np.std(spread)
        if std == 0:
            return None

        z = (bar.close - mean - mu) / std

        if z > self.entry_z and (self.position is None or self.position.size == 0):
            return Signal(action="sell", price=bar.close, metadata={"z": z, "kappa": kappa})
        if z < -self.entry_z and (self.position is None or self.position.size == 0):
            return Signal(action="buy", price=bar.close, metadata={"z": z, "kappa": kappa})
        if abs(z) < self.exit_z and self.position is not None:
            return Signal(action="close", metadata={"z": z})
        return None

    def warmup_period(self) -> int:
        return self.lookback

    def get_params(self) -> dict[str, Any]:
        return {"lookback": self.lookback, "entry_z": self.entry_z, "exit_z": self.exit_z}