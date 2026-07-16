from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

# OKX-tiered maintenance margin rate (simplified, notional in USD).
# Borrowed concept from Vibe-Trading's tiered table — larger positions
# require a higher maintenance margin, which triggers liquidation earlier.
_TIER_TABLE = [
    (100_000, 0.004),
    (500_000, 0.006),
    (1_000_000, 0.01),
    (5_000_000, 0.02),
    (10_000_000, 0.05),
    (float("inf"), 0.10),
]


def tiered_maintenance_rate(notional_usd: float) -> float:
    """Look up tiered maintenance margin rate by position notional."""
    for tier_max, rate in _TIER_TABLE:
        if notional_usd <= tier_max:
            return rate
    return _TIER_TABLE[-1][1]


@dataclass
class LiquidationError(Exception):
    mark_price: float
    liquidation_price: float

class PerpSimulator:
    """Leverage / margin / mark-price liquidation for perpetual futures."""
    def __init__(self, maintenance_margin_rate: float = 0.005, use_tiered: bool = True):
        self.maintenance_margin_rate = maintenance_margin_rate
        self.use_tiered = use_tiered

    def _maint_rate(self, notional: float) -> float:
        if self.use_tiered:
            return tiered_maintenance_rate(notional)
        return self.maintenance_margin_rate

    def margin_required(self, notional: float, leverage: float) -> float:
        return notional / leverage

    def liquidation_price(self, entry_price: float, leverage: float, side: int, notional: float | None = None) -> float:
        """Price at which a position is liquidated (before fees)."""
        maint = self._maint_rate(notional) if notional is not None else self.maintenance_margin_rate
        # loss from entry to liq must equal initial margin*(1 - maint) for the position
        # long: liq = entry * (1 - (1 - maint)/leverage)
        # short: liq = entry * (1 + (1 - maint)/leverage)
        factor = (1 - maint) / leverage
        if side > 0:
            return entry_price * (1 - factor)
        return entry_price * (1 + factor)

    def check_liquidation(self, mark_price: float, entry_price: float, size: float, leverage: float, notional: float | None = None) -> bool:
        """size>0 = long, size<0 = short. Returns True if position is liquidated at mark_price."""
        side = 1 if size > 0 else -1
        liq = self.liquidation_price(entry_price, leverage, side, notional)
        if side > 0:
            return mark_price <= liq
        return mark_price >= liq
