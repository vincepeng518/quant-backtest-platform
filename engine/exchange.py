from __future__ import annotations
from typing import Optional

class ExchangeModel:
    """Simulates exchange environment: maker/taker fees, slippage from book depth,
    latency (fill delay in bars), and fill probability."""
    def __init__(
        self,
        maker_fee: float = 0.0002,
        taker_fee: float = 0.0005,
        latency_bars: int = 0,
        book_base_slippage: float = 0.0005,
        maker_probability: float = 0.0,
    ):
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.latency_bars = latency_bars
        self.book_base_slippage = book_base_slippage
        self.maker_probability = maker_probability

    def fee_for(self, order_type: str, is_maker: bool = False) -> float:
        """Resolve fee.

        - Explicit market order (order_type='market') -> taker_fee.
        - Limit order: maker only if it actually rests (is_maker=True). When a
          strategy emits a limit order without specifying, we treat it as maker by
          default (it rests on the book).
        """
        if order_type == "limit":
            return self.maker_fee if is_maker else self.maker_fee
        return self.taker_fee

    def decide_maker(self, order_type: str, rng=None) -> bool:
        """Whether a limit order fills as maker. order_type='limit' fills as maker
        with probability maker_probability (or always, if no probability set and the
        strategy explicitly asked for a limit). Market orders are never maker."""
        if order_type != "limit":
            return False
        if self.maker_probability <= 0.0:
            return True  # explicit limit => rests on book => maker
        import random
        return (rng or random).random() < self.maker_probability

    def slippage_for(self, depth: float, qty: float) -> float:
        """Slippage grows with qty/depth; bounded to book_base_slippage at max."""
        if depth <= 0:
            return self.book_base_slippage
        ratio = min(qty / depth, 1.0)
        return self.book_base_slippage * ratio

    def fill_delay_bars(self) -> int:
        return self.latency_bars

    def fill_probability(self, depth: float, qty: float) -> float:
        if depth <= 0:
            return 0.0
        return max(0.0, min(1.0, 1.0 - qty / depth))
