"""
測試事件定義

驗證：
- 事件是 frozen dataclass（immutable）
- 欄位正確
- 從 pandas row 建立 BarEvent
- SignalType / OrderSide 枚舉正確
"""
import pytest
import pandas as pd
from datetime import datetime

from events import (
    Event, EventType, BarEvent, SignalEvent, SignalType,
    OrderEvent, OrderSide, OrderType, FillEvent, SLTPEvent,
)


class TestBarEvent:
    """BarEvent 測試"""

    def test_create_from_row(self):
        """從 pandas row 建立 BarEvent"""
        row = pd.Series({
            "open": 100, "high": 105, "low": 95,
            "close": 102, "volume": 1000,
        }, name=pd.Timestamp("2024-01-01"))
        bar = BarEvent.from_row(row.name, row, symbol="BTC/USDT")
        assert bar.timestamp == pd.Timestamp("2024-01-01")
        assert bar.open == 100
        assert bar.high == 105
        assert bar.low == 95
        assert bar.close == 102
        assert bar.volume == 1000
        assert bar.symbol == "BTC/USDT"
        assert bar.type == EventType.BAR

    def test_from_row_missing_volume(self):
        """沒 volume 欄位時用 0"""
        row = pd.Series({
            "open": 100, "high": 105, "low": 95, "close": 102,
        }, name=pd.Timestamp("2024-01-01"))
        bar = BarEvent.from_row(row.name, row)
        assert bar.volume == 0

    def test_immutable(self):
        """BarEvent 是 frozen（不可變）"""
        bar = BarEvent(timestamp=pd.Timestamp("2024-01-01"), close=100)
        with pytest.raises(Exception):  # FrozenInstanceError
            bar.close = 200

    def test_default_type(self):
        """type 預設為 EventType.BAR"""
        bar = BarEvent(timestamp=pd.Timestamp("2024-01-01"), close=100)
        assert bar.type == EventType.BAR


class TestSignalEvent:
    """SignalEvent 測試"""

    def test_long_entry_signal(self):
        sig = SignalEvent(
            timestamp=pd.Timestamp("2024-01-01"),
            signal_type=SignalType.LONG_ENTRY,
        )
        assert sig.signal_type == SignalType.LONG_ENTRY
        assert sig.type == EventType.SIGNAL
        assert sig.strength == 1.0  # 預設

    def test_custom_strength(self):
        sig = SignalEvent(
            timestamp=pd.Timestamp("2024-01-01"),
            signal_type=SignalType.SHORT_ENTRY,
            strength=0.5,
        )
        assert sig.strength == 0.5


class TestOrderEvent:
    """OrderEvent 測試"""

    def test_market_order(self):
        order = OrderEvent(
            timestamp=pd.Timestamp("2024-01-01"),
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
        )
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.MARKET
        assert order.price is None
        assert order.is_close is False  # 預設新倉單

    def test_close_order_flag(self):
        """is_close 標記平倉單"""
        order = OrderEvent(
            timestamp=pd.Timestamp("2024-01-01"),
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=1.0,
            is_close=True,
        )
        assert order.is_close is True

    def test_limit_order_with_price(self):
        order = OrderEvent(
            timestamp=pd.Timestamp("2024-01-01"),
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.5,
            price=100.0,
        )
        assert order.order_type == OrderType.LIMIT
        assert order.price == 100.0


class TestFillEvent:
    """FillEvent 測試"""

    def test_create(self):
        fill = FillEvent(
            timestamp=pd.Timestamp("2024-01-01"),
            side=OrderSide.BUY,
            quantity=1.0,
            price=100.5,
            commission=0.1,
            slippage=0.0005,
        )
        assert fill.type == EventType.FILL
        assert fill.price == 100.5
        assert fill.commission == 0.1
        assert fill.is_close is False  # 預設


class TestEventType:
    """EventType 枚舉測試"""

    def test_values(self):
        assert EventType.BAR.value == "bar"
        assert EventType.SIGNAL.value == "signal"
        assert EventType.ORDER.value == "order"
        assert EventType.FILL.value == "fill"
        assert EventType.SL_TP.value == "sl_tp"


class TestSignalType:
    """SignalType 枚舉測試"""

    def test_all_four_types(self):
        types = {SignalType.LONG_ENTRY, SignalType.LONG_EXIT,
                 SignalType.SHORT_ENTRY, SignalType.SHORT_EXIT}
        assert len(types) == 4
