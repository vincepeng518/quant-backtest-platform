from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass
class LiquidationError(Exception):
    mark_price: float
    liquidation_price: float

class PerpSimulator:
    """Leverage / margin / mark-price liquidation for perpetual futures."""
    def __init__(self, maintenance_margin_rate: float = 0.005):
        self.maintenance_margin_rate = maintenance_margin_rate

    def margin_required(self, notional: float, leverage: float) -> float:
        return notional / leverage

    def liquidation_price(self, entry_price: float, leverage: float, side: int) -> float:
        """Price at which a position is liquidated (before fees)."""
        # loss from entry to liq must equal initial margin*(1 - maint) for the position
        # long: liq = entry * (1 - (1 - maint)/leverage)
        # short: liq = entry * (1 + (1 - maint)/leverage)
        factor = (1 - self.maintenance_margin_rate) / leverage
        if side > 0:
            return entry_price * (1 - factor)
        return entry_price * (1 + factor)

    def check_liquidation(self, mark_price: float, entry_price: float, size: float, leverage: float) -> bool:
        """size>0 = long, size<0 = short. Returns True if position is liquidated at mark_price."""
        side = 1 if size > 0 else -1
        liq = self.liquidation_price(entry_price, leverage, side)
        if side > 0:
            return mark_price <= liq
        return mark_price >= liq
