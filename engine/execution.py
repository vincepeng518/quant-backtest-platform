from __future__ import annotations

"""ExecutionModel — realistic fill simulation (borrowed from NautilusTrader / polybot).

Our old backtester assumed fills happen at mid price with a fixed slippage
constant. Real markets have:
  - spread (ticks): limit orders fill at bid/ask, not mid
  - fill probability: a limit order may not fill (or partially fill)
  - latency: signal -> order arrives N ms later, price moved
  - thin liquidity: need a synthetic book to model partial fills

This module models all four. Each MarketEngine owns one ExecutionModel.
"""

import math
import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExecutionConfig:
    """Tunable realism knobs. Defaults = zero-latency perfect-fill (legacy behavior)."""
    slippage_ticks: float = 0.0          # additive tick slippage on market orders
    entry_slippage_pct: float = 0.0      # % slippage on entry
    exit_slippage_pct: float = 0.0       # % slippage on exit
    prob_fill_on_limit: float = 1.0      # P(limit order fills if price touches)
    latency_ms: float = 0.0              # signal->order latency (affects fill price)
    min_synthetic_book_size: float = 0.0 # if >0, model thin liquidity via synthetic book
    tick_size: float = 0.01              # market tick size (for ticks->price)


class ExecutionModel:
    def __init__(self, cfg: Optional[ExecutionConfig] = None) -> None:
        self.cfg = cfg or ExecutionConfig()

    # ── price impact ──
    def fill_price(self, ref_price: float, side: str, is_entry: bool) -> float:
        """Return the effective fill price given a reference (mid) price.

        side: 'buy' / 'sell'  |  is_entry: True for open, False for close
        """
        c = self.cfg
        slip_pct = c.entry_slippage_pct if is_entry else c.exit_slippage_pct
        # direction: buyer pays up, seller receives down
        direction = 1.0 if side in ("buy", "long") else -1.0
        tick_slip = c.slippage_ticks * c.tick_size
        impacted = ref_price * (1.0 + direction * (slip_pct + tick_slip / max(ref_price, 1e-9)))
        return impacted

    # ── fill probability ──
    def will_fill(self, order_type: str = "market") -> bool:
        """Decide if an order fills. Market orders always fill; limit orders use prob."""
        if order_type == "market":
            return True
        return random.random() < self.cfg.prob_fill_on_limit

    # ── latency adjustment ──
    def latency_price_drift(self, ref_price: float, side: str) -> float:
        """Approximate price drift during latency window.

        A crude but useful model: assume volatility scales drift ~ latency_ms.
        We use a small fixed fraction so it's deterministic-ish without market data.
        """
        if self.cfg.latency_ms <= 0:
            return 0.0
        # 0.0001 per 100ms as a conservative drift proxy
        drift = (self.cfg.latency_ms / 100.0) * 0.0001
        direction = 1.0 if side in ("buy", "long") else -1.0
        return ref_price * drift * direction

    # ── thin liquidity cap ──
    def cap_size_to_liquidity(self, desired_size: float, visible_liquidity: float) -> float:
        """Cap order size to available book liquidity (synthetic or real)."""
        if self.cfg.min_synthetic_book_size > 0:
            return min(desired_size, self.cfg.min_synthetic_book_size)
        if visible_liquidity > 0:
            return min(desired_size, visible_liquidity)
        return desired_size
