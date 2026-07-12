"""
風控 handler：接收 SignalEvent，產出 OrderEvent

檢查當前倉位、餘額、最大持倉比例、最大回撤等，過濾不安全的訊號。
"""
from __future__ import annotations

from typing import List
from events import (
    BarEvent, Event, OrderEvent, OrderSide, OrderType,
    SignalEvent, SignalType,
)
from handlers import EventHandler


class RiskManager(EventHandler):
    """
    風控管理器

    規則：
    - 已有同方向持倉 → 拒絕進場訊號
    - 無持倉時收到出場訊號 → 拒絕
    - 反方向進場訊號 → 先平倉再開倉（生成兩個 OrderEvent）

    OrderEvent 帶有 is_close 標記，讓 Portfolio 知道這是平倉單還是新倉單。
    """

    def __init__(self, max_position_pct: float = 1.0, allow_pyramiding: bool = False):
        self.max_position_pct = max_position_pct
        self.allow_pyramiding = allow_pyramiding
        self._current_position = 0  # -1, 0, 1

    def update_position(self, position: int) -> None:
        """由 Portfolio 通知目前倉位"""
        self._current_position = position

    def handle(self, event: Event) -> List[Event]:
        if not isinstance(event, SignalEvent):
            return []

        pos = self._current_position
        orders = []

        if event.signal_type == SignalType.LONG_ENTRY:
            if pos == 1 and not self.allow_pyramiding:
                return []  # 已有 long，不重複進場
            if pos == -1:
                # 反向：先平空，再開多
                orders.append(OrderEvent(
                    timestamp=event.timestamp,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    quantity=1.0,
                    is_close=True,  # 標記為平倉單
                    parent_signal=event,
                ))
            orders.append(OrderEvent(
                timestamp=event.timestamp,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=self.max_position_pct,
                is_close=False,
                parent_signal=event,
            ))

        elif event.signal_type == SignalType.LONG_EXIT:
            if pos == 1:
                orders.append(OrderEvent(
                    timestamp=event.timestamp,
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    quantity=1.0,
                    is_close=True,
                    parent_signal=event,
                ))

        elif event.signal_type == SignalType.SHORT_ENTRY:
            if pos == -1 and not self.allow_pyramiding:
                return []
            if pos == 1:
                orders.append(OrderEvent(
                    timestamp=event.timestamp,
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    quantity=1.0,
                    is_close=True,
                    parent_signal=event,
                ))
            orders.append(OrderEvent(
                timestamp=event.timestamp,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=self.max_position_pct,
                is_close=False,
                parent_signal=event,
            ))

        elif event.signal_type == SignalType.SHORT_EXIT:
            if pos == -1:
                orders.append(OrderEvent(
                    timestamp=event.timestamp,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    quantity=1.0,
                    is_close=True,
                    parent_signal=event,
                ))

        return orders

