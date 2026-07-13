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
    ):
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.latency_bars = latency_bars
        self.book_base_slippage = book_base_slippage

    def fee_for(self, order_type: str, is_maker: bool) -> float:
        """order_type 'limit' with is_maker=True -> maker_fee; 'market' or taker -> taker_fee."""
        if order_type == "limit" and is_maker:
            return self.maker_fee
        return self.taker_fee

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
