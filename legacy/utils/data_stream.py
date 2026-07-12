"""
行情資料流訂閱接口（WebSocket 預埋）

為未來實盤行情做準備。目前為 stub，定義接口規範。
未來實作時只需填入實際的 WebSocket 連線邏輯。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Dict
import logging

logger = logging.getLogger(__name__)


class DataStreamSubscriber(ABC):
    """行情資料流訂閱者抽象基底類別"""

    @abstractmethod
    def subscribe(self, symbol: str, timeframe: str, callback: Callable) -> None:
        ...

    @abstractmethod
    def unsubscribe(self, symbol: str) -> None:
        ...

    @abstractmethod
    def close(self) -> None:
        ...


class CCXTWebSocketStream(DataStreamSubscriber):
    """CCXT WebSocket 行情訂閱器（stub）"""

    def __init__(self, exchange_id: str = "bingx"):
        self.exchange_id = exchange_id
        self._subscriptions: Dict[str, Callable] = {}
        self._running = False

    def subscribe(self, symbol: str, timeframe: str, callback: Callable) -> None:
        key = f"{symbol}_{timeframe}"
        self._subscriptions[key] = callback
        logger.info(f"WebSocket subscribe: {key} (stub)")

    def unsubscribe(self, symbol: str) -> None:
        keys_to_remove = [k for k in self._subscriptions if k.startswith(symbol)]
        for k in keys_to_remove:
            del self._subscriptions[k]

    def close(self) -> None:
        self._subscriptions.clear()
        self._running = False
        logger.info("WebSocket connections closed (stub)")


class RealtimeBarStorage:
    """即時 K 線存儲（SQLite stub）"""

    def __init__(self, db_path: str = "data/realtime.db"):
        self.db_path = db_path

    def upsert_bar(self, symbol: str, timeframe: str, bar: dict) -> None:
        pass

    def get_latest_bars(self, symbol: str, timeframe: str, limit: int = 100) -> list:
        return []


__all__ = ["DataStreamSubscriber", "CCXTWebSocketStream", "RealtimeBarStorage"]
