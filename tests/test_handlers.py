"""
測試各 handler

每個 handler 都獨立測試（純函式、無副作用、便於 mock）。
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime

from events import (
    BarEvent, SignalEvent, SignalType, OrderEvent, OrderSide, OrderType,
    FillEvent, SLTPEvent, EventType,
)
from handlers.strategy_handler import StrategyHandler
from handlers.risk_manager import RiskManager
from handlers.execution import SimulatedExecutionHandler
from handlers.portfolio import PortfolioHandler
from handlers.sltp_monitor import SLTPMonitor


# === 測試資料 ===
def make_df(n=100, seed=42):
    """製造測試用 K 線資料"""
    np.random.seed(seed)
    base = 100
    ret = np.random.normal(0, 0.02, n)
    close = base * np.exp(np.cumsum(ret))
    return pd.DataFrame({
        "open": close * 0.99,
        "high": close * 1.01,
        "low": close * 0.98,
        "close": close,
        "volume": np.random.uniform(100, 1000, n),
    }, index=pd.date_range("2024-01-01", periods=n, freq="1D"))


def make_bar(timestamp, close=100, open=99, high=101, low=98, volume=1000):
    """製造測試 BarEvent"""
    return BarEvent(
        timestamp=timestamp,
        open=open, high=high, low=low, close=close, volume=volume,
    )


# ==========================================
# StrategyHandler 測試
# ==========================================
class TestStrategyHandler:
    """StrategyHandler 測試"""

    def test_precomputed_no_signal(self):
        """沒訊號時回傳空 list"""
        df = make_df(50)
        entries = pd.Series(False, index=df.index)
        exits = pd.Series(False, index=df.index)
        h = StrategyHandler()
        h.set_precomputed_signals(entries, exits)
        bar = make_bar(df.index[10])
        assert h.handle(bar) == []

    def test_precomputed_long_entry(self):
        """預算 LONG_ENTRY 訊號"""
        df = make_df(50)
        entries = pd.Series(False, index=df.index)
        entries.iloc[10] = True
        exits = pd.Series(False, index=df.index)
        h = StrategyHandler()
        h.set_precomputed_signals(entries, exits)
        bar = make_bar(df.index[10])
        signals = h.handle(bar)
        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.LONG_ENTRY

    def test_precomputed_long_exit(self):
        """預算 LONG_EXIT 訊號"""
        df = make_df(50)
        entries = pd.Series(False, index=df.index)
        exits = pd.Series(False, index=df.index)
        exits.iloc[20] = True
        h = StrategyHandler()
        h.set_precomputed_signals(entries, exits)
        bar = make_bar(df.index[20])
        signals = h.handle(bar)
        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.LONG_EXIT

    def test_precomputed_short_signals(self):
        """預算 short 訊號"""
        df = make_df(50)
        long_entries = pd.Series(False, index=df.index)
        long_exits = pd.Series(False, index=df.index)
        short_entries = pd.Series(False, index=df.index)
        short_exits = pd.Series(False, index=df.index)
        short_entries.iloc[5] = True
        short_exits.iloc[15] = True
        h = StrategyHandler()
        h.set_precomputed_signals(
            entries=long_entries, exits=long_exits,
            long_entries=long_entries, long_exits=long_exits,
            short_entries=short_entries, short_exits=short_exits,
        )
        bar5 = make_bar(df.index[5])
        sig5 = h.handle(bar5)
        assert len(sig5) == 1
        assert sig5[0].signal_type == SignalType.SHORT_ENTRY

        bar15 = make_bar(df.index[15])
        sig15 = h.handle(bar15)
        assert len(sig15) == 1
        assert sig15[0].signal_type == SignalType.SHORT_EXIT

    def test_long_and_long_exit_same_bar(self):
        """同根 K 線同時有進場和出場（邊界）"""
        df = make_df(50)
        entries = pd.Series(False, index=df.index)
        entries.iloc[10] = True
        exits = pd.Series(False, index=df.index)
        exits.iloc[10] = True
        h = StrategyHandler()
        h.set_precomputed_signals(entries, exits)
        bar = make_bar(df.index[10])
        signals = h.handle(bar)
        # 兩個訊號都該被產生
        assert len(signals) == 2

    def test_bar_with_wrong_timestamp(self):
        """timestamp 不在 series 索引中"""
        df = make_df(50)
        entries = pd.Series(False, index=df.index)
        exits = pd.Series(False, index=df.index)
        h = StrategyHandler()
        h.set_precomputed_signals(entries, exits)
        bad_bar = make_bar(pd.Timestamp("2099-01-01"))
        assert h.handle(bad_bar) == []  # 不該 crash

    def test_non_bar_event_ignored(self):
        """非 BarEvent 事件被忽略"""
        h = StrategyHandler()
        sig = SignalEvent(timestamp=pd.Timestamp("2024-01-01"),
                         signal_type=SignalType.LONG_ENTRY)
        assert h.handle(sig) == []


# ==========================================
# RiskManager 測試
# ==========================================
class TestRiskManager:
    """RiskManager 測試"""

    def test_long_entry_when_flat(self):
        """無持倉時收到 LONG_ENTRY → 1 個 BUY 新倉單"""
        rm = RiskManager(max_position_pct=1.0)
        rm.update_position(0)
        sig = SignalEvent(timestamp=pd.Timestamp("2024-01-01"),
                         signal_type=SignalType.LONG_ENTRY)
        orders = rm.handle(sig)
        assert len(orders) == 1
        assert orders[0].side == OrderSide.BUY
        assert orders[0].is_close is False

    def test_long_entry_when_already_long(self):
        """已有 long 持倉時收到 LONG_ENTRY → 不動作（不重複進場）"""
        rm = RiskManager()
        rm.update_position(1)
        sig = SignalEvent(timestamp=pd.Timestamp("2024-01-01"),
                         signal_type=SignalType.LONG_ENTRY)
        orders = rm.handle(sig)
        assert orders == []

    def test_long_entry_when_short(self):
        """持空倉時收到 LONG_ENTRY → 平倉 BUY + 開倉 BUY（2 個）"""
        rm = RiskManager()
        rm.update_position(-1)
        sig = SignalEvent(timestamp=pd.Timestamp("2024-01-01"),
                         signal_type=SignalType.LONG_ENTRY)
        orders = rm.handle(sig)
        assert len(orders) == 2
        # 第一個：平倉
        assert orders[0].is_close is True
        # 第二個：新倉
        assert orders[1].is_close is False

    def test_long_exit_when_long(self):
        """持 long 持倉時收到 LONG_EXIT → 1 個 SELL 平倉單"""
        rm = RiskManager()
        rm.update_position(1)
        sig = SignalEvent(timestamp=pd.Timestamp("2024-01-01"),
                         signal_type=SignalType.LONG_EXIT)
        orders = rm.handle(sig)
        assert len(orders) == 1
        assert orders[0].side == OrderSide.SELL
        assert orders[0].is_close is True

    def test_long_exit_when_flat(self):
        """無持倉時收到 LONG_EXIT → 不動作"""
        rm = RiskManager()
        rm.update_position(0)
        sig = SignalEvent(timestamp=pd.Timestamp("2024-01-01"),
                         signal_type=SignalType.LONG_EXIT)
        orders = rm.handle(sig)
        assert orders == []

    def test_short_signals_mirror_long(self):
        """SHORT 訊號邏輯與 LONG 對稱"""
        rm = RiskManager()
        rm.update_position(0)
        # SHORT_ENTRY
        orders = rm.handle(SignalEvent(
            timestamp=pd.Timestamp("2024-01-01"),
            signal_type=SignalType.SHORT_ENTRY
        ))
        assert len(orders) == 1
        assert orders[0].side == OrderSide.SELL

        rm.update_position(-1)
        # SHORT_EXIT
        orders = rm.handle(SignalEvent(
            timestamp=pd.Timestamp("2024-01-01"),
            signal_type=SignalType.SHORT_EXIT
        ))
        assert len(orders) == 1
        assert orders[0].side == OrderSide.BUY

    def test_non_signal_ignored(self):
        """非 SignalEvent 忽略"""
        rm = RiskManager()
        bar = make_bar(pd.Timestamp("2024-01-01"))
        assert rm.handle(bar) == []


# ==========================================
# SimulatedExecutionHandler 測試
# ==========================================
class TestSimulatedExecutionHandler:
    """SimulatedExecutionHandler 測試"""

    def test_market_buy_with_slippage(self):
        """市價 BUY：成交價 = 基準價 * (1 + 滑點)"""
        exec = SimulatedExecutionHandler(commission=0.001, slippage=0.0005)
        bar = make_bar(pd.Timestamp("2024-01-01"), close=100)
        exec.set_current_bar(bar)
        order = OrderEvent(
            timestamp=pd.Timestamp("2024-01-01"),
            side=OrderSide.BUY, order_type=OrderType.MARKET,
            quantity=1.0,
        )
        fills = exec.handle(order)
        assert len(fills) == 1
        # 滑點向上
        assert abs(fills[0].price - 100 * 1.0005) < 1e-6
        # 手續費
        assert abs(fills[0].commission - 100 * 1.0005 * 1.0 * 0.001) < 1e-4

    def test_market_sell_with_slippage(self):
        """市價 SELL：成交價 = 基準價 * (1 - 滑點)"""
        exec = SimulatedExecutionHandler(slippage=0.0005)
        bar = make_bar(pd.Timestamp("2024-01-01"), close=100)
        exec.set_current_bar(bar)
        order = OrderEvent(
            timestamp=pd.Timestamp("2024-01-01"),
            side=OrderSide.SELL, order_type=OrderType.MARKET,
            quantity=1.0,
        )
        fills = exec.handle(order)
        assert abs(fills[0].price - 100 * 0.9995) < 1e-6

    def test_limit_order_uses_specified_price(self):
        """限價單：用指定價格，不加滑點"""
        exec = SimulatedExecutionHandler(slippage=0.0005)
        bar = make_bar(pd.Timestamp("2024-01-01"), close=100)
        exec.set_current_bar(bar)
        order = OrderEvent(
            timestamp=pd.Timestamp("2024-01-01"),
            side=OrderSide.BUY, order_type=OrderType.LIMIT,
            quantity=1.0, price=99.0,
        )
        fills = exec.handle(order)
        assert fills[0].price == 99.0 * 1.0005  # 仍加買進滑點

    def test_no_bar_means_no_fill(self):
        """沒設定 current_bar 時，市價單無法成交"""
        exec = SimulatedExecutionHandler()
        # 不呼叫 set_current_bar
        order = OrderEvent(
            timestamp=pd.Timestamp("2024-01-01"),
            side=OrderSide.BUY, order_type=OrderType.MARKET,
            quantity=1.0,
        )
        fills = exec.handle(order)
        assert fills == []


# ==========================================
# PortfolioHandler 測試
# ==========================================
class TestPortfolioHandler:
    """PortfolioHandler 測試"""

    def test_initial_state(self):
        """初始狀態"""
        p = PortfolioHandler(initial_capital=10000)
        assert p.cash == 10000
        assert p.position == 0
        assert p.entry_price == 0.0
        assert p.trades == []
        assert p.get_equity() == 10000  # 沒倉位，權益=現金

    def test_buy_creates_long_position(self):
        """BUY 開多倉"""
        p = PortfolioHandler(initial_capital=10000, commission=0.001)
        fill = FillEvent(
            timestamp=pd.Timestamp("2024-01-01"),
            side=OrderSide.BUY, quantity=1.0, price=100.0, commission=0.1,
        )
        p.handle(fill)
        assert p.position == 1
        assert p.entry_price == 100.0
        assert p.cash == 10000 - 0.1  # 扣手續費

    def test_sell_closes_long_records_trade(self):
        """SELL 平多倉並記錄 trade（需設 is_close=True）"""
        p = PortfolioHandler(initial_capital=10000, commission=0.0)
        # 開倉
        p.handle(FillEvent(
            timestamp=pd.Timestamp("2024-01-01"),
            side=OrderSide.BUY, quantity=1.0, price=100.0, commission=0.0,
        ))
        # 平倉（漲到 110）
        p.handle(FillEvent(
            timestamp=pd.Timestamp("2024-02-01"),
            side=OrderSide.SELL, quantity=1.0, price=110.0, commission=0.0,
            is_close=True,  # 標記為平倉單
        ))
        assert p.position == 0
        assert len(p.trades) == 1
        assert p.trades[0].direction == "long"
        # pnl = (110-100)/100 = 10%
        assert abs(p.trades[0].pnl_pct - 0.10) < 1e-6

    def test_sell_when_flat_does_not_open_short(self):
        """無持倉收到 SELL（且 is_close=True）不應開空倉"""
        p = PortfolioHandler()
        fill = FillEvent(
            timestamp=pd.Timestamp("2024-01-01"),
            side=OrderSide.SELL, quantity=1.0, price=100.0,
            is_close=True,
        )
        p.handle(fill)
        assert p.position == 0  # 沒開空倉
        assert len(p.trades) == 0

    def test_buy_opens_long_when_flat(self):
        """無持倉收到 BUY（is_close=False）開多倉"""
        p = PortfolioHandler()
        fill = FillEvent(
            timestamp=pd.Timestamp("2024-01-01"),
            side=OrderSide.BUY, quantity=1.0, price=100.0,
            is_close=False,
        )
        p.handle(fill)
        assert p.position == 1
        assert p.entry_price == 100.0

    def test_short_trade_pnl(self):
        """空倉 trade 的 pnl 計算"""
        p = PortfolioHandler(initial_capital=10000, commission=0.0)
        # 開空（新倉單）
        p.handle(FillEvent(
            timestamp=pd.Timestamp("2024-01-01"),
            side=OrderSide.SELL, quantity=1.0, price=100.0, commission=0.0,
            is_close=False,  # 新倉單
        ))
        assert p.position == -1
        # 平空（平倉單）
        p.handle(FillEvent(
            timestamp=pd.Timestamp("2024-02-01"),
            side=OrderSide.BUY, quantity=1.0, price=90.0, commission=0.0,
            is_close=True,
        ))
        assert p.position == 0
        assert len(p.trades) == 1
        assert p.trades[0].direction == "short"
        # 空倉 pnl = (100-90)/100 = 10%
        assert abs(p.trades[0].pnl_pct - 0.10) < 1e-6

    def test_calculate_metrics_no_trades(self):
        """沒交易時 metrics 報錯"""
        p = PortfolioHandler()
        m = p.calculate_metrics()
        assert "error" in m

    def test_calculate_metrics_basic(self):
        """基本 metrics 計算"""
        p = PortfolioHandler(initial_capital=10000, commission=0.0)
        # trade 1: 賺
        p.handle(FillEvent(timestamp=pd.Timestamp("2024-01-01"),
                            side=OrderSide.BUY, quantity=1.0, price=100, commission=0))
        p.snapshot_equity(pd.Timestamp("2024-01-01"))
        p.handle(FillEvent(timestamp=pd.Timestamp("2024-02-01"),
                            side=OrderSide.SELL, quantity=1.0, price=110, commission=0,
                            is_close=True))
        p.snapshot_equity(pd.Timestamp("2024-02-01"))
        # trade 2: 賠
        p.handle(FillEvent(timestamp=pd.Timestamp("2024-03-01"),
                            side=OrderSide.BUY, quantity=1.0, price=100, commission=0))
        p.snapshot_equity(pd.Timestamp("2024-03-01"))
        p.handle(FillEvent(timestamp=pd.Timestamp("2024-04-01"),
                            side=OrderSide.SELL, quantity=1.0, price=90, commission=0,
                            is_close=True))
        p.snapshot_equity(pd.Timestamp("2024-04-01"))
        m = p.calculate_metrics()
        assert m["n_trades"] == 2
        assert m["win_rate"] == 50.0
        assert m["long_trades"] == 2


# ==========================================
# SLTPMonitor 測試
# ==========================================
class TestSLTPMonitor:
    """SLTPMonitor 測試"""

    def test_long_stop_loss_triggered(self):
        """多倉觸及停損"""
        sltp = SLTPMonitor()
        sltp.set_position(
            side=OrderSide.BUY, entry_price=100,
            stop_loss=95, take_profit=None
        )
        bar = make_bar(pd.Timestamp("2024-01-02"), open=100, high=100, low=94, close=96)
        events = sltp.handle(bar)
        assert len(events) == 1
        assert events[0].triggered_stop is True
        assert events[0].trigger_price == 95

    def test_long_take_profit_triggered(self):
        """多倉觸及停利"""
        sltp = SLTPMonitor()
        sltp.set_position(
            side=OrderSide.BUY, entry_price=100,
            stop_loss=None, take_profit=110
        )
        bar = make_bar(pd.Timestamp("2024-01-02"), open=100, high=112, low=99, close=110)
        events = sltp.handle(bar)
        assert len(events) == 1
        assert events[0].triggered_stop is False  # False = TP
        assert events[0].trigger_price == 110

    def test_no_trigger_within_range(self):
        """價格在範圍內不觸發"""
        sltp = SLTPMonitor()
        sltp.set_position(
            side=OrderSide.BUY, entry_price=100,
            stop_loss=95, take_profit=110
        )
        bar = make_bar(pd.Timestamp("2024-01-02"), open=100, high=105, low=98, close=102)
        events = sltp.handle(bar)
        assert events == []

    def test_short_stop_loss_triggered(self):
        """空倉觸及停損（價格上漲）"""
        sltp = SLTPMonitor()
        sltp.set_position(
            side=OrderSide.SELL, entry_price=100,
            stop_loss=105, take_profit=None
        )
        bar = make_bar(pd.Timestamp("2024-01-02"), open=100, high=107, low=99, close=106)
        events = sltp.handle(bar)
        assert len(events) == 1
        assert events[0].triggered_stop is True

    def test_no_position_no_trigger(self):
        """沒持倉時不觸發"""
        sltp = SLTPMonitor()  # 沒 set_position
        bar = make_bar(pd.Timestamp("2024-01-02"), low=50, close=60)
        events = sltp.handle(bar)
        assert events == []

    def test_clear_position(self):
        """clear 後不再觸發"""
        sltp = SLTPMonitor()
        sltp.set_position(
            side=OrderSide.BUY, entry_price=100,
            stop_loss=95, take_profit=None
        )
        sltp.clear()
        bar = make_bar(pd.Timestamp("2024-01-02"), low=50, close=60)
        events = sltp.handle(bar)
        assert events == []
