from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

from strategies.base import Bar, Signal, StrategyBase
from strategies.factor.factors import compute_factor, FACTOR_REGISTRY


class FactorStrategy(StrategyBase):
    """Factor-driven strategy: combine multiple factors into a composite score.

    Each factor produces a raw value; we z-score it over a trailing window to
    make factors comparable, then take a weighted sum -> composite score.
    Score crosses +entry_threshold => long; crosses -entry_threshold => short;
    returns toward 0 (or opposite cross) => close.

    This is the factor layer the user requested: a strategy that is *driven*
    by a vector of factors, not a hand-coded single-rule signal.
    """

    name = "factor_driven"
    description = "因子驅動策略 (多因子 z-score 加權合成 → 信號)"
    category = "factor"

    def __init__(self) -> None:
        super().__init__()
        self._history: list[float] = []
        self._factor_history: dict[str, list[float]] = {}

    def init(self, params: dict[str, Any]) -> None:
        self.params = params
        # factors: list of {name, window, weight}
        self.factors = params.get("factors") or [
            {"name": "momentum", "window": 20, "weight": 1.0},
            {"name": "mean_reversion", "window": 20, "weight": -0.5},
            {"name": "rsi", "window": 14, "weight": -0.3},
        ]
        self.z_window = int(params.get("z_window", 60))
        self.entry_threshold = float(params.get("entry_threshold", 1.0))
        self.exit_threshold = float(params.get("exit_threshold", 0.2))
        self._history.clear()
        self._factor_history.clear()

    def next(self, bar: Bar) -> Optional[Signal]:
        self._history.append(bar.close)
        if len(self._history) < max(f["window"] for f in self.factors) + 2:
            return None

        close = pd.Series(self._history)
        # compute raw factor values
        raw: dict[str, float] = {}
        for f in self.factors:
            fn_name = f["name"]
            if fn_name not in FACTOR_REGISTRY:
                continue
            val = compute_factor(fn_name, close, window=f.get("window", 20))
            raw[fn_name] = val
            self._factor_history.setdefault(fn_name, []).append(val)

        # z-score each factor over trailing z_window
        composite = 0.0
        total_w = 0.0
        for f in self.factors:
            fn_name = f["name"]
            if fn_name not in raw:
                continue
            hist = self._factor_history.get(fn_name, [])
            if len(hist) < 2:
                z = 0.0
            else:
                arr = np.array(hist[-self.z_window:])
                mu = arr.mean()
                sd = arr.std()
                z = (raw[fn_name] - mu) / sd if sd > 1e-12 else 0.0
            w = float(f.get("weight", 1.0))
            composite += z * w
            total_w += abs(w)
        if total_w > 0:
            composite /= total_w  # normalized to ~unitless z-space

        # position state via self.position (kept in sync by Backtester)
        has_pos = self.position is not None and abs(self.position.size) > 1e-9
        direction = 1 if (self.position is not None and self.position.size > 0) else (-1 if (self.position is not None and self.position.size < 0) else 0)

        if not has_pos:
            if composite >= self.entry_threshold:
                return Signal(action="buy", order_type="market", metadata={"composite": round(composite, 3), "factors": raw})
            if composite <= -self.entry_threshold:
                return Signal(action="sell", order_type="market", metadata={"composite": round(composite, 3), "factors": raw})
            return None

        # exit logic
        if direction > 0 and composite <= self.exit_threshold:
            return Signal(action="close", order_type="market", metadata={"composite": round(composite, 3)})
        if direction < 0 and composite >= -self.exit_threshold:
            return Signal(action="close", order_type="market", metadata={"composite": round(composite, 3)})
        return None

    def get_params(self) -> dict[str, Any]:
        return {
            "factors": self.factors,
            "z_window": self.z_window,
            "entry_threshold": self.entry_threshold,
            "exit_threshold": self.exit_threshold,
        }

    def get_params_space(self) -> dict[str, Any]:
        return {
            "z_window": [30, 60, 120],
            "entry_threshold": [0.5, 1.0, 1.5, 2.0],
            "exit_threshold": [0.0, 0.2, 0.5],
        }
