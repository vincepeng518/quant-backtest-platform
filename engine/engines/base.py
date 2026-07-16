from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from engine.execution import ExecutionConfig, ExecutionModel


@dataclass
class PositionState:
    """Mutable position state shared with the engine."""
    size: float
    entry_price: float
    direction: int = 1  # +1 long, -1 short
    leverage: float = 1.0
    entry_bar_index: Optional[int] = None
    entry_time: Any = None
    notional: float = 0.0

    @property
    def is_open(self) -> bool:
        return abs(self.size) > 1e-12


class MarketEngine(ABC):
    """Abstract market-rule engine.

    The Backtester owns the bar loop, capital, and equity curve. All
    *market-specific* behaviour (fees, slippage, leverage, funding,
    liquidation, trading-session gating) is delegated here so a single
    Backtester can run crypto / equity / forex with zero branching.

    This mirrors the design Vibe-Trading uses (BaseEngine + per-market
    subclasses) but keeps our existing funding/perp models intact.
    """

    # ── Trading session ──
    @abstractmethod
    def can_execute(self, timestamp: pd.Timestamp) -> bool:
        """Whether new orders may be placed on this bar's timestamp."""
        ...

    # ── Costs ──
    @abstractmethod
    def commission(self, notional: float, is_open: bool) -> float:
        """Absolute commission cost for a fill."""
        ...

    @abstractmethod
    def slippage_factor(self, direction: int) -> float:
        """Multiplier applied to price (1 ± slip). +1 long, -1 short."""
        ...

    # ── Position sizing ──
    @abstractmethod
    def position_size(self, capital: float, price: float, leverage: float) -> float:
        """Size (in units) for a full-capital deployment."""
        ...

    # ── Per-bar hooks (funding, liquidation, swap, etc.) ──
    @abstractmethod
    def on_bar(
        self,
        bar: pd.Series,
        timestamp: pd.Timestamp,
        position: Optional[PositionState],
    ) -> dict:
        """Run per-bar market hooks.

        Returns a dict that may contain:
          - 'funding_fee': float (deducted from capital)
          - 'liquidated': bool (position forcibly closed this bar)
          - 'swap_fee': float
        The Backtester applies these to capital / position.
        """
        ...

    # ── Liquidation price (for UI / markers) ──
    def liquidation_price(self, pos: PositionState) -> Optional[float]:
        """Return liquidation price if applicable, else None."""
        return None

    # ── Display metadata ──
    @property
    def market_type(self) -> str:
        return "base"

    def __init__(self, exec_cfg: Optional[ExecutionConfig] = None) -> None:
        self.exec_model = ExecutionModel(exec_cfg)
