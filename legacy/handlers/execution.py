"""
模擬交易所 handler：接收 OrderEvent，產出 FillEvent

計算滑點、手續費、回傳模擬成交。
"""
from __future__ import annotations

from typing import List, Optional
from events import Event, FillEvent, OrderEvent, OrderSide, BarEvent
from handlers import EventHandler


class SimulatedExecutionHandler(EventHandler):
    """
    模擬交易所

    市價單：用同一根 K 線的 close 成交（加滑點）
    限價單：用指定 price 成交
    """

    def __init__(self, commission: float = 0.001, slippage: float = 0.0005):
        self.commission = commission
        self.slippage = slippage
        self._order_counter = 0
        self._current_bar: Optional[BarEvent] = None

    def set_current_bar(self, bar: BarEvent) -> None:
        """由 EventEngine 通知當前正在處理的 BarEvent"""
        self._current_bar = bar

    def handle(self, event: Event) -> List[Event]:
        if not isinstance(event, OrderEvent):
            return []

        self._order_counter += 1
        order_id = f"order_{self._order_counter}"

        # 決定成交價
        if event.price is None or event.price == 0.0:
            # 市價單：用當前 K 線 close
            if self._current_bar is None:
                fill_price = 0.0
            else:
                fill_price = self._current_bar.close
        else:
            fill_price = event.price

        if fill_price == 0.0:
            # 無法成交
            return []

        if event.side == OrderSide.BUY:
            fill_price = fill_price * (1 + self.slippage)
        else:
            fill_price = fill_price * (1 - self.slippage)

        quantity = event.quantity
        commission_cost = abs(fill_price * quantity * self.commission)

        return [FillEvent(
            timestamp=event.timestamp,
            side=event.side,
            quantity=quantity,
            price=fill_price,
            commission=commission_cost,
            slippage=self.slippage,
            order_id=order_id,
            is_close=getattr(event, 'is_close', False),
        )]

