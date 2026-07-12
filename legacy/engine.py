"""
事件驅動回測引擎（核心）

EventEngine 接收 K 線資料，按時間順序分發 BarEvent 給各 handler，
各 handler 產出的新事件也會被分發給其他 handler（直到沒有新事件為止）。
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Dict, List, Optional
import pandas as pd

from events import (
    BarEvent, Event, EventType, FillEvent, OrderEvent,
    SLTPEvent,
)
from handlers import EventHandler
from handlers.strategy_handler import StrategyHandler
from handlers.risk_manager import RiskManager
from handlers.execution import SimulatedExecutionHandler
from handlers.portfolio import PortfolioHandler
from handlers.sltp_monitor import SLTPMonitor


logger = logging.getLogger(__name__)


class EventEngine:
    """
    事件驅動回測引擎

    資料流：
        BarEvent → StrategyHandler → SignalEvent(s)
                            ↓
                  RiskManager → OrderEvent(s)
                            ↓
              SimulatedExecution → FillEvent
                            ↓
                  PortfolioHandler (更新持倉/現金/權益)

        每根 BarEvent 也會觸發 SLTPMonitor（產生 SLTPEvent → OrderEvent）
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        commission: float = 0.001,
        slippage: float = 0.0005,
        max_position_pct: float = 1.0,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ):
        # 初始化各 handler
        self.strategy = None  # 由 set_strategy 設定
        self.risk = RiskManager(max_position_pct=max_position_pct)
        self.execution = SimulatedExecutionHandler(commission=commission, slippage=slippage)
        self.portfolio = PortfolioHandler(initial_capital=initial_capital, commission=commission)
        self.sltp = SLTPMonitor()

        self.stop_loss = stop_loss
        self.take_profit = take_profit

        # handler 路由：event_type → 處理它的 handler list
        self._routes: Dict[EventType, List[EventHandler]] = {
            EventType.BAR: [self.strategy, self.sltp],  # 動態加入
            EventType.SIGNAL: [self.risk],
            EventType.ORDER: [self.execution],
            EventType.FILL: [self.portfolio],
            EventType.SL_TP: [self._sltp_to_order],  # 內建 converter
        }
        # 動態：strategy 設進去後補上 BAR 路由
        self._strategy_handler_ref: Optional[EventHandler] = None

        # 事件佇列
        self._queue: deque = deque()

    def set_strategy(self, strategy_code: str, params: dict, df: pd.DataFrame) -> None:
        """設定策略（用整個 df 預熱歷史）"""
        if self.strategy is None:
            self.strategy = StrategyHandler()
        self.strategy.set_dynamic_strategy(strategy_code, params, df)
        # 重新註冊 BAR 路由
        self._routes[EventType.BAR] = [self.strategy, self.sltp]

    def set_precomputed_signals(
        self,
        entries: pd.Series,
        exits: pd.Series,
        long_entries=None,
        long_exits=None,
        short_entries=None,
        short_exits=None,
    ) -> None:
        """設定預算的 series（向後相容用）"""
        if self.strategy is None:
            self.strategy = StrategyHandler()
        self.strategy.set_precomputed_signals(
            entries, exits, long_entries, long_exits, short_entries, short_exits
        )
        self._routes[EventType.BAR] = [self.strategy, self.sltp]

    def _sltp_to_order(self, event: Event) -> List[Event]:
        """SLTPEvent → 觸發平倉 OrderEvent"""
        if not isinstance(event, SLTPEvent):
            return []
        from events import OrderEvent, OrderSide, OrderType
        pos = self.portfolio.get_position()
        if pos == 0:
            return []
        # 送出平倉單
        close_side = OrderSide.SELL if pos == 1 else OrderSide.BUY
        return [OrderEvent(
            timestamp=event.timestamp,
            side=close_side,
            order_type=OrderType.MARKET,
            quantity=1.0,
            price=event.trigger_price,
        )]

    def _dispatch(self, event: Event) -> None:
        """分發單一事件給所有相關 handler"""
        handlers = self._routes.get(event.type, [])
        # 通知 execution handler 當前 BarEvent（讓市價單能成交）
        if isinstance(event, BarEvent):
            self.execution.set_current_bar(event)
        for h in handlers:
            try:
                new_events = h.handle(event)
                for ne in new_events:
                    self._queue.append(ne)
            except Exception as e:
                logger.exception(f"Handler {type(h).__name__} 處理 {event.type} 失敗: {e}")
        # 任何成交/倉位變化都即時同步給 RiskManager
        if isinstance(event, FillEvent):
            self.risk.update_position(self.portfolio.position)

    def run(self, df: pd.DataFrame, symbol: str = "") -> Dict:
        """
        執行事件驅動回測

        Args:
            df: OHLCV 資料
            symbol: 標的名稱

        Returns:
            與舊版相容的回測結果 dict
        """
        if self.strategy is None:
            raise ValueError("請先呼叫 set_strategy()")

        # 把每根 K 線塞進 queue
        for timestamp, row in df.iterrows():
            bar = BarEvent.from_row(timestamp, row, symbol=symbol)
            self._queue.append(bar)
            # 設定 SLTP 監控
            if self.stop_loss or self.take_profit:
                from events import OrderSide
                # 當前若有持倉，設定 SLTP
                pos = self.portfolio.get_position()
                if pos != 0 and self.portfolio.entry_time is not None:
                    side = OrderSide.BUY if pos == 1 else OrderSide.SELL
                    if pos == 1:
                        sl_price = self.portfolio.entry_price * (1 - (self.stop_loss or 0)) if self.stop_loss else None
                        tp_price = self.portfolio.entry_price * (1 + (self.take_profit or 0)) if self.take_profit else None
                    else:
                        sl_price = self.portfolio.entry_price * (1 + (self.stop_loss or 0)) if self.stop_loss else None
                        tp_price = self.portfolio.entry_price * (1 - (self.take_profit or 0)) if self.take_profit else None
                    self.sltp.set_position(side, self.portfolio.entry_price, sl_price, tp_price)
                else:
                    self.sltp.clear()

            # 處理 queue 中所有事件（直到空）
            while self._queue:
                ev = self._queue.popleft()
                self._dispatch(ev)

            # 同步 RiskManager 持倉
            self.risk.update_position(self.portfolio.position)

            # 記錄權益快照
            self.portfolio.snapshot_equity(timestamp)

        # 最後一個 bar 收盤時，若有持倉則平倉
        if self.portfolio.position != 0:
            from events import FillEvent, OrderEvent, OrderSide, OrderType
            close_side = OrderSide.SELL if self.portfolio.position == 1 else OrderSide.BUY
            order = OrderEvent(
                timestamp=df.index[-1],
                side=close_side,
                order_type=OrderType.MARKET,
                quantity=1.0,
                price=df["close"].iloc[-1],
                is_close=True,
            )
            self._dispatch(order)
            # 處理後續 FillEvent 等事件
            while self._queue:
                ev = self._queue.popleft()
                self._dispatch(ev)
            self.risk.update_position(self.portfolio.position)

        # 構造與舊版相容的結果
        return {
            "data": self.portfolio.build_equity_dataframe(),
            "trades": [
                {
                    "entry_time": t.entry_time,
                    "exit_time": t.exit_time,
                    "direction": t.direction,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "pnl_pct": t.pnl_pct,
                    "pnl": t.pnl,
                    "duration_hours": t.duration_hours,
                    "exit_reason": t.exit_reason,
                }
                for t in self.portfolio.trades
            ],
            "metrics": self.portfolio.calculate_metrics(),
        }
