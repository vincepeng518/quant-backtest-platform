"""
停損/停利監控 handler：接收 BarEvent + 訂單，產出 SLTPEvent

每根 K 線檢查持倉是否觸及停損/停利。
"""
from __future__ import annotations

from typing import List, Optional
from events import BarEvent, Event, OrderEvent, OrderSide, SLTPEvent
from handlers import EventHandler


class SLTPMonitor(EventHandler):
    """停損/停利監控"""

    def __init__(self):
        self._position_side: Optional[OrderSide] = None
        self._entry_price: float = 0.0
        self._stop_loss: Optional[float] = None
        self._take_profit: Optional[float] = None

    def set_position(self, side: Optional[OrderSide], entry_price: float,
                     stop_loss: Optional[float], take_profit: Optional[float]) -> None:
        """當有新持倉時呼叫"""
        self._position_side = side
        self._entry_price = entry_price
        self._stop_loss = stop_loss
        self._take_profit = take_profit

    def clear(self) -> None:
        self._position_side = None
        self._entry_price = 0.0
        self._stop_loss = None
        self._take_profit = None

    def handle(self, event: Event) -> List[Event]:
        if not isinstance(event, BarEvent) or self._position_side is None:
            return []

        events = []

        # 多倉：停損 = entry * (1 - pct)，停利 = entry * (1 + pct)
        if self._position_side == OrderSide.BUY:
            if self._stop_loss and event.low <= self._stop_loss:
                events.append(SLTPEvent(
                    timestamp=event.timestamp,
                    triggered_stop=True,
                    trigger_price=self._stop_loss,
                ))
            elif self._take_profit and event.high >= self._take_profit:
                events.append(SLTPEvent(
                    timestamp=event.timestamp,
                    triggered_stop=False,
                    trigger_price=self._take_profit,
                ))
        elif self._position_side == OrderSide.SELL:
            if self._stop_loss and event.high >= self._stop_loss:
                events.append(SLTPEvent(
                    timestamp=event.timestamp,
                    triggered_stop=True,
                    trigger_price=self._stop_loss,
                ))
            elif self._take_profit and event.low <= self._take_profit:
                events.append(SLTPEvent(
                    timestamp=event.timestamp,
                    triggered_stop=False,
                    trigger_price=self._take_profit,
                ))

        return events
