from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from engine.engines.base import MarketEngine, PositionState
from engine.execution import ExecutionConfig


# Simplified swap table (points per lot, long/short). Wednesday triple swap.
_SWAP_LONG = {"EUR/USD": -6.5, "GBP/USD": -3.0, "USD/JPY": 8.0, "USD/CHF": 4.0,
              "AUD/USD": -2.0, "USD/CAD": 2.0, "NZD/USD": -1.5}
_SWAP_SHORT = {"EUR/USD": 3.5, "GBP/USD": -1.0, "USD/JPY": -12.0, "USD/CHF": -8.0,
               "AUD/USD": -1.0, "USD/CAD": -5.0, "NZD/USD": -2.0}


class ForexEngine(MarketEngine):
    """Forex: 24/5 sessions, spread-based cost, overnight swap.

    - Trades Sunday 22:00 UTC → Friday 22:00 UTC (gaps on weekends).
    - Cost = spread (in price terms) rather than commission pct.
    - Swap charged daily at 00:00 UTC, triple on Wednesday.
    """

    def __init__(
        self,
        spread_pips: float = 0.0001,   # fractional spread (e.g. 1 pip on EUR/USD)
        contract_size: float = 100_000,
        leverage: float = 30.0,
        exec_cfg: Optional[ExecutionConfig] = None,
    ) -> None:
        super().__init__(exec_cfg)
        self.spread = spread_pips
        self.contract_size = contract_size
        self.leverage = leverage
        self._last_swap_date: Optional[Any] = None

    @property
    def market_type(self) -> str:
        return "forex"

    def can_execute(self, timestamp: pd.Timestamp) -> bool:
        # 24/5: closed on Saturday (and Sunday before 22:00, Friday after 22:00)
        dow = timestamp.dayofweek
        if dow == 5:  # Saturday
            return False
        if dow == 6 and timestamp.hour < 22:
            return False
        if dow == 4 and timestamp.hour >= 22:
            return False
        return True

    def commission(self, notional: float, is_open: bool) -> float:
        # Spread already captured in slippage_factor; commission = 0 for raw FX
        return 0.0

    def slippage_factor(self, direction: int) -> float:
        # Spread applied as half on each side (entry adverse by spread/2)
        return 1.0 + direction * (self.spread / 2.0)

    def position_size(self, capital: float, price: float, leverage: float) -> float:
        if price <= 0:
            return 0.0
        # lots = capital * leverage / (contract_size * price)
        notional = capital * leverage
        return notional / price

    def on_bar(self, bar: pd.Series, timestamp: pd.Timestamp, position: Optional[PositionState]) -> dict:
        result: dict[str, Any] = {"funding_fee": 0.0, "liquidated": False, "swap_fee": 0.0}
        if position is None or not position.is_open:
            return result
        # Daily swap at 00:00 UTC
        cur_date = timestamp.date()
        if self._last_swap_date != cur_date and timestamp.hour == 0:
            self._last_swap_date = cur_date
            pair = getattr(position, "symbol", "EUR/USD")
            long_swap = _SWAP_LONG.get(pair, -1.0)
            short_swap = _SWAP_SHORT.get(pair, -1.0)
            swap_pts = long_swap if position.direction > 0 else short_swap
            mult = 3.0 if timestamp.weekday() == 2 else 1.0  # Wed triple
            lots = abs(position.size) / self.contract_size
            result["swap_fee"] = lots * swap_pts * mult * position.entry_price
        return result
