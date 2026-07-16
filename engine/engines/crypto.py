from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from engine.engines.base import MarketEngine, PositionState
from engine.funding import FundingModel
from engine.perpetual import PerpSimulator
from engine.execution import ExecutionConfig


class CryptoEngine(MarketEngine):
    """Crypto perpetual: 24/7, maker/taker fees, funding, leverage liquidation."""

    def __init__(
        self,
        maker_rate: float = 0.0002,
        taker_rate: float = 0.0005,
        slippage: float = 0.0005,
        funding: Optional[FundingModel] = None,
        perp: Optional[PerpSimulator] = None,
        leverage: float = 1.0,
        exec_cfg: Optional[ExecutionConfig] = None,
    ) -> None:
        super().__init__(exec_cfg)
        self.maker_rate = maker_rate
        self.taker_rate = taker_rate
        self.slippage = slippage
        self.funding = funding
        self.perp = perp
        self.leverage = leverage
        # funding dedup bookkeeping
        self._funding_applied: set = set()
        self._funding_daily_done: set = set()

    @property
    def market_type(self) -> str:
        return "crypto"

    def can_execute(self, timestamp: pd.Timestamp) -> bool:
        return True  # 24/7

    def commission(self, notional: float, is_open: bool) -> float:
        rate = self.taker_rate if is_open else self.maker_rate
        return notional * rate

    def slippage_factor(self, direction: int) -> float:
        return 1.0 + direction * self.slippage

    def position_size(self, capital: float, price: float, leverage: float) -> float:
        if price <= 0:
            return 0.0
        return (capital * leverage) / price

    def on_bar(self, bar: pd.Series, timestamp: pd.Timestamp, position: Optional[PositionState]) -> dict:
        result: dict[str, Any] = {"funding_fee": 0.0, "liquidated": False, "swap_fee": 0.0}
        if position is None or not position.is_open:
            return result

        # ── Funding fee (8h settlement) ──
        if self.funding is not None:
            rate = self.funding.rate_at(timestamp)
            if rate != 0.0:
                # charge funding only at settlement hours (0/8/16 UTC) to avoid
                # per-bar double counting; FundingModel already accrues correctly
                # when called at close, but we gate here for the live on_bar path.
                if timestamp.hour in {0, 8, 16}:
                    notional = position.size * position.entry_price
                    result["funding_fee"] = notional * rate * position.direction

        # ── Liquidation check ──
        if self.perp is not None:
            mark = float(bar.get("close", position.entry_price))
            notional = abs(position.size) * position.entry_price
            if self.perp.check_liquidation(mark, position.entry_price, position.size, self.leverage, notional):
                result["liquidated"] = True

        return result

    def liquidation_price(self, pos: PositionState) -> Optional[float]:
        if self.perp is None or pos.leverage <= 1.0:
            return None
        notional = abs(pos.size) * pos.entry_price
        return self.perp.liquidation_price(pos.entry_price, pos.leverage, pos.direction, notional)
