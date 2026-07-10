"""
事件驅動回測引擎 - 事件定義

所有事件都是 frozen dataclass（immutable），可在 queue/handler 之間安全傳遞。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
import pandas as pd


# === 事件類型枚舉 ===
class EventType(str, Enum):
    BAR = "bar"               # 新的 K 線
    SIGNAL = "signal"          # 策略產生的訊號
    ORDER = "order"            # 風控後產生的訂單
    FILL = "fill"              # 模擬成交
    SL_TP = "sl_tp"            # 停損/停利觸發
    RISK = "risk"              # 風控事件（drawdown 過大等）


# === 基礎事件 ===
@dataclass(frozen=True)
class Event:
    """所有事件的基底類別"""
    type: EventType
    timestamp: datetime


# === K 線事件 ===
@dataclass(frozen=True)
class BarEvent(Event):
    """一根 K 線（任何時間框架）"""
    type: EventType = field(default=EventType.BAR, init=False)
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0
    symbol: str = ""

    @classmethod
    def from_row(cls, timestamp, row: pd.Series, symbol: str = "") -> "BarEvent":
        """從 pandas row 建立 BarEvent"""
        return cls(
            timestamp=timestamp,
            open=float(row.get("open", row.get("close", 0))),
            high=float(row.get("high", row.get("close", 0))),
            low=float(row.get("low", row.get("close", 0))),
            close=float(row["close"]),
            volume=float(row.get("volume", 0)),
            symbol=symbol,
        )


# === 訊號事件（策略產出） ===
class SignalType(str, Enum):
    LONG_ENTRY = "LONG_ENTRY"      # 做多進場
    LONG_EXIT = "LONG_EXIT"        # 做多出場
    SHORT_ENTRY = "SHORT_ENTRY"    # 做空進場
    SHORT_EXIT = "SHORT_EXIT"      # 做空出場


@dataclass(frozen=True)
class SignalEvent(Event):
    """策略產生的訊號"""
    type: EventType = field(default=EventType.SIGNAL, init=False)
    signal_type: SignalType = SignalType.LONG_ENTRY
    strength: float = 1.0           # 訊號強度（0-1，可選）
    reason: str = ""                 # 訊號原因（debug 用）


# === 訂單事件（風控後產出） ===
class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


@dataclass(frozen=True)
class OrderEvent(Event):
    """要送給模擬交易所的訂單"""
    type: EventType = field(default=EventType.ORDER, init=False)
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.MARKET
    quantity: float = 0.0
    price: Optional[float] = None    # None = 市價
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    parent_signal: Optional[SignalEvent] = None
    is_close: bool = False            # True=平倉單, False=新倉單


# === 成交事件（模擬交易所回傳） ===
@dataclass(frozen=True)
class FillEvent(Event):
    """模擬成交回報"""
    type: EventType = field(default=EventType.FILL, init=False)
    side: OrderSide = OrderSide.BUY
    quantity: float = 0.0
    price: float = 0.0
    commission: float = 0.0
    slippage: float = 0.0
    order_id: str = ""
    is_close: bool = False


# === 停損/停利事件（內部產生） ===
@dataclass(frozen=True)
class SLTPEvent(Event):
    """停損或停利被觸發"""
    type: EventType = field(default=EventType.SL_TP, init=False)
    triggered_stop: bool = False     # True=停損, False=停利
    trigger_price: float = 0.0
