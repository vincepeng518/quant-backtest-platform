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
    """Phase 2 訂單簿深度源抽象。可插拔：predict.fun / Polymarket / mock。"""

    @abstractmethod
    def fetch_book(self, market_id: str) -> Optional[BookSnapshot]:
        """拉取目標市場訂單簿快照 (sync: 由引擎熱路徑呼叫)。"""
        ...


class PredictFunBookSource(OrderBookSource):
    """predict.fun GraphQL 訂單簿源 (主戰場, 公開無需 auth)。

    透過 `monitoring.predictfun.PredictFunSource.book_for(market_id)`
    取得 [[price, size], ...] 階梯，轉換為 BookSnapshot。
    """

    def __init__(self) -> None:
        from monitoring.predictfun import PredictFunSource
        self._src = PredictFunSource()

    def fetch_book(self, market_id: str) -> Optional[BookSnapshot]:
        book = self._src.book_for(market_id)
        if not book:
            return None
        bids = book.get("bids") or []
        asks = book.get("asks") or []
        if not bids and not asks:
            return None
        # predict.fun bids/asks: [[price, size], ...] 已排序 (bids 降冪, asks 升冪)
        best_bid = float(bids[0][0]) if bids else 0.0
        best_ask = float(asks[0][0]) if asks else (best_bid + 0.01 if best_bid else 0.0)
        bid_size = float(bids[0][1]) if bids else 0.0
        ask_size = float(asks[0][1]) if asks else 0.0
        # 累計 0.60~0.75 區間掛單量 (買方吃單價落在此區間的流動性)
        depth = 0.0
        for lvl in (bids + asks):
            try:
                p = float(lvl[0])
            except (TypeError, ValueError, IndexError):
                continue
            if 0.60 <= p <= 0.75:
                depth += float(lvl[1])
        return BookSnapshot(
            bid=best_bid, ask=best_ask, bid_size=bid_size, ask_size=ask_size,
            spread=best_ask - best_bid, depth_at_60_75=depth, raw=book,
        )

    def close(self):
        try:
            self._src.close()
        except Exception:
            pass


class PolymarketClobSource(OrderBookSource):
    """Polymarket CLOB REST /book —— 已驗證可用，暫作深度代理。
    TODO: 已被 predict.fun GraphQL 源取代 (見 PredictFunBookSource)。
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
        depth = 0.0
        for lvl in asks:
            p = float(lvl["price"])
            if 0.60 <= p <= 0.75:
                depth += float(lvl.get("size", 0))
        return BookSnapshot(
            bid=best_bid, ask=best_ask, bid_size=bid_size, ask_size=ask_size,
            spread=best_ask - best_bid, depth_at_60_75=depth, raw=d,
        )
