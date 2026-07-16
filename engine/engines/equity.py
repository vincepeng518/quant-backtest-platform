from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from engine.engines.base import MarketEngine, PositionState


class EquityEngine(MarketEngine):
    """Equity (stocks/ETFs): no leverage, no funding, T+1 fill, weekday sessions.

    Mirrors a cash equity account:
      - Trades only on business days (Mon–Fri, no weekend gaps).
      - A signal generated on bar N fills on the NEXT bar's open (T+1),
        preventing look-ahead on daily closes.
      - Fixed commission per trade (absolute USD) or pct of notional.
      - No liquidation (no margin).
    """

    def __init__(
        self,
        commission_pct: float = 0.0005,
        commission_min: float = 1.0,   # many brokers enforce a min ticket fee
        slippage: float = 0.0002,
        t1_delay: bool = True,
    ) -> None:
        self.commission_pct = commission_pct
        self.commission_min = commission_min
        self.slippage = slippage
        self.t1_delay = t1_delay

    @property
    def market_type(self) -> str:
        return "equity"

    def can_execute(self, timestamp: pd.Timestamp) -> bool:
        # Business day only (handles holidays implicitly via data gaps)
        return timestamp.dayofweek < 5

    def commission(self, notional: float, is_open: bool) -> float:
        fee = notional * self.commission_pct
        return max(fee, self.commission_min)

    def slippage_factor(self, direction: int) -> float:
        return 1.0 + direction * self.slippage

    def position_size(self, capital: float, price: float, leverage: float = 1.0) -> float:
        if price <= 0:
            return 0.0
        return capital / price  # no leverage for equities

    def on_bar(self, bar: pd.Series, timestamp: pd.Timestamp, position: Optional[PositionState]) -> dict:
        # No funding, no liquidation for cash equities.
        return {"funding_fee": 0.0, "liquidated": False, "swap_fee": 0.0}
