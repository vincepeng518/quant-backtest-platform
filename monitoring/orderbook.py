from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class BookSnapshot:
    bid: float            # best bid price (USDC per share, 0~1)
    ask: float            # best ask price
    bid_size: float       # best bid size (shares)
    ask_size: float
    spread: float
    # 指定價位區間的累計掛單量 (流動性代理)
    depth_at_60_75: float = 0.0
    raw: Optional[dict] = None


class OrderBookSource(ABC):
    """Phase 2 訂單簿深度源抽象。可插拔：Polymarket / predict.fun / mock。"""

    @abstractmethod
    def fetch_book(self, market_id: str) -> Optional[BookSnapshot]:
        """拉取目標市場訂單簿快照 (sync: 由引擎熱路徑呼叫)。"""
        ...


class PolymarketClobSource(OrderBookSource):
    """Polymarket CLOB REST /book —— 已驗證可用，暫作深度代理。
    TODO: 替換為 predict.fun BNB Chain CLOB endpoint（主戰場）。
    """

    BASE = "https://clob.polymarket.com"

    def __init__(self, token_id: str) -> None:
        self.token_id = token_id

    def fetch_book(self, market_id: str = "") -> Optional[BookSnapshot]:
        import httpx
        try:
            with httpx.Client(timeout=10.0) as c:
                r = c.get(f"{self.BASE}/book", params={"token_id": self.token_id})
                r.raise_for_status()
                d = r.json()
        except Exception:
            return None
        bids = d.get("bids") or []
        asks = d.get("asks") or []
        if not bids or not asks:
            return None
        best_bid = float(bids[0]["price"])
        best_ask = float(asks[0]["price"])
        bid_size = float(bids[0].get("size", 0))
        ask_size = float(asks[0].get("size", 0))
        # 累計 0.60~0.75 區間掛單量 (買方吃單價落在這區間的流動性)
        depth = 0.0
        for lvl in asks:
            p = float(lvl["price"])
            if 0.60 <= p <= 0.75:
                depth += float(lvl.get("size", 0))
        return BookSnapshot(
            bid=best_bid, ask=best_ask, bid_size=bid_size, ask_size=ask_size,
            spread=best_ask - best_bid, depth_at_60_75=depth, raw=d,
        )
