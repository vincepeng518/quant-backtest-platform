from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any, Optional

import numpy as np

from strategies.base import Bar, Signal, StrategyBase


class PairsTradingStrategy(StrategyBase):
    """配對交易：基於雙標的價差 Z-Score 的均值回歸。

    在 init 時透過 BingX 預載第二標的（symbol_b）全程收盤價，
    next 中與主標的收盤價計算價差（ratio 法）並做 Z-Score 訊號。
    """

    name = "pairs_trading"
    description = "配對交易策略"
    category = "mean_reversion"

    def init(self, params: dict[str, Any]) -> None:
        super().init(params)
        self.window = int(params.get("window", 100))
        self.entry_z = float(params.get("entry_z", 2.0))
        self.exit_z = float(params.get("exit_z", 0.5))
        self.symbol_b = params.get("symbol_b", "ETH/USDT")
        self.spread: list[float] = []
        self.leg2: list[float] = []
        self._load_leg2()

    @lru_cache(maxsize=8)
    def _fetch_close(self, symbol: str, timeframe: str = "1h") -> tuple:
        try:
            import ccxt

            ex = ccxt.bingx()
            ex.timeout = 20000
            raw = ex.fetch_ohlcv(symbol, timeframe, limit=1500)
            return tuple(r[4] for r in raw)  # close prices
        except Exception:
            return tuple()

    def _load_leg2(self) -> None:
        try:
            closes = self._fetch_close(self.symbol_b)
            self.leg2 = list(closes)
        except Exception:
            self.leg2 = []

    def _calc_zscore(self) -> float:
        arr = np.array(self.spread)
        mean, std = np.mean(arr), np.std(arr)
        return (arr[-1] - mean) / std if std > 0 else 0.0

    def next(self, bar: Bar) -> Optional[Signal]:
        idx = len(self.spread)
        # Build hedge ratio spread: log(leg1) - log(leg2); fall back to leg1 alone
        if idx < len(self.leg2) and self.leg2[idx] > 0:
            spread_val = float(np.log(bar.close) - np.log(self.leg2[idx]))
        else:
            spread_val = bar.close
        self.spread.append(spread_val)

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
        return {
            "window": self.window,
            "entry_z": self.entry_z,
            "exit_z": self.exit_z,
            "symbol_b": self.symbol_b,
        }

    def get_params_space(self) -> dict[str, Any]:
        return {
            "window": {"type": "range", "min": 30, "max": 300, "step": 5},
            "entry_z": {"type": "range", "min": 1.0, "max": 3.0, "step": 0.1},
            "exit_z": {"type": "range", "min": 0.1, "max": 1.0, "step": 0.1},
        }
