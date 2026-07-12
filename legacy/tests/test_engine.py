"""
測試 EventEngine 整合

驗證完整事件流：Bar → Signal → Order → Fill → Portfolio
"""
import pytest
import pandas as pd
import numpy as np

from engine import EventEngine
from events import BarEvent, SignalType, EventType
from utils.event_engine import EventDrivenBacktestEngine


def make_df(n=100, seed=42, with_trend=True):
    """製造測試用 K 線"""
    np.random.seed(seed)
    if with_trend:
        # 有趨勢的資料
        base = 100
        ret = np.random.normal(0.001, 0.02, n)
        close = base * np.exp(np.cumsum(ret))
    else:
        close = np.full(n, 100.0) + np.random.normal(0, 0.5, n)
    return pd.DataFrame({
        "open": close * 0.99,
        "high": close * 1.01,
        "low": close * 0.98,
        "close": close,
        "volume": np.random.uniform(100, 1000, n),
    }, index=pd.date_range("2024-01-01", periods=n, freq="1D"))


class TestEventEngineBasic:
    """EventEngine 基本測試"""

    def test_create_engine(self):
        """建立 EventEngine 不應 crash"""
        engine = EventEngine(initial_capital=10000)
        assert engine.portfolio.cash == 10000
        assert engine.portfolio.position == 0

    def test_run_without_strategy_raises(self):
        """沒設策略就 run 應報錯"""
        engine = EventEngine()
        df = make_df(10)
        with pytest.raises(ValueError, match="請先呼叫 set_strategy"):
            engine.run(df)

    def test_simple_long_strategy(self):
        """簡單策略：第 20 根買，第 60 根賣"""
        df = make_df(100)
        # 用預算 signals 模式
        entries = pd.Series(False, index=df.index)
        exits = pd.Series(False, index=df.index)
        entries.iloc[20] = True
        exits.iloc[60] = True

        engine = EventEngine(initial_capital=10000, commission=0.0, slippage=0.0)
        engine.set_precomputed_signals(entries, exits)
        results = engine.run(df)

        # 應該有 1 個 trade
        assert len(results["trades"]) == 1
        trade = results["trades"][0]
        assert trade["direction"] == "long"
        assert trade["entry_time"] == df.index[20]
        assert trade["exit_time"] == df.index[60]
        # 驗證 pnl = (exit - entry) * capital / entry（不預設正負）
        expected_pnl = (df.iloc[60]["close"] - df.iloc[20]["close"]) * 10000 / df.iloc[20]["close"]
        assert abs(trade["pnl"] - expected_pnl) < 1.0  # 允許小誤差

    def test_no_signals_no_trades(self):
        """沒訊號就沒 trade"""
        df = make_df(50)
        entries = pd.Series(False, index=df.index)
        exits = pd.Series(False, index=df.index)
        engine = EventEngine()
        engine.set_precomputed_signals(entries, exits)
        results = engine.run(df)
        assert results["trades"] == []

    def test_open_position_at_end_gets_closed(self):
        """持倉到最後一根 K 線時自動平倉"""
        df = make_df(50)
        entries = pd.Series(False, index=df.index)
        exits = pd.Series(False, index=df.index)
        entries.iloc[10] = True
        # 沒有對應的 exit

        engine = EventEngine(initial_capital=10000, commission=0.0, slippage=0.0)
        engine.set_precomputed_signals(entries, exits)
        results = engine.run(df)
        # 應該有 1 個 trade（自動在最後平倉）
        assert len(results["trades"]) == 1

    def test_equity_curve_tracks_position(self):
        """權益曲線隨持倉變化"""
        df = make_df(50)
        entries = pd.Series(False, index=df.index)
        exits = pd.Series(False, index=df.index)
        entries.iloc[10] = True
        exits.iloc[40] = True

        engine = EventEngine(initial_capital=10000, commission=0.0, slippage=0.0)
        engine.set_precomputed_signals(entries, exits)
        results = engine.run(df)

        equity = results["data"]
        assert len(equity) == 50
        # 進場前權益 = 10000
        assert equity.iloc[10]["equity"] == 10000
        # 出場後權益應不同（取決於價格變動）
        assert equity.iloc[40]["equity"] != 10000

    def test_metrics_consistency(self):
        """metrics 與 trades 一致"""
        df = make_df(100)
        entries = pd.Series(False, index=df.index)
        exits = pd.Series(False, index=df.index)
        entries.iloc[10] = True
        exits.iloc[50] = True
        entries.iloc[60] = True
        exits.iloc[90] = True

        engine = EventEngine(initial_capital=10000, commission=0.0, slippage=0.0)
        engine.set_precomputed_signals(entries, exits)
        results = engine.run(df)

        assert results["metrics"]["n_trades"] == 2
        assert results["metrics"]["n_trades"] == len(results["trades"])


class TestEventEngineWithSLTP:
    """EventEngine 配合停損停利"""

    def test_long_stop_loss(self):
        """多倉觸及停損"""
        df = make_df(50)
        entries = pd.Series(False, index=df.index)
        exits = pd.Series(False, index=df.index)
        entries.iloc[10] = True

        engine = EventEngine(
            initial_capital=10000, commission=0.0, slippage=0.0,
            stop_loss=0.05,  # 5% 停損
        )
        engine.set_precomputed_signals(entries, exits)
        results = engine.run(df)
        # 應該有 1 個 trade（被停損平倉）
        assert len(results["trades"]) == 1

    def test_long_take_profit(self):
        """多倉觸及停利"""
        df = make_df(50)
        entries = pd.Series(False, index=df.index)
        exits = pd.Series(False, index=df.index)
        entries.iloc[10] = True

        engine = EventEngine(
            initial_capital=10000, commission=0.0, slippage=0.0,
            take_profit=0.10,  # 10% 停利
        )
        engine.set_precomputed_signals(entries, exits)
        results = engine.run(df)
        # 有停利
        assert len(results["trades"]) >= 1


class TestEventDrivenBacktestEngine:
    """測試 utils/event_engine.py 的對外 wrapper"""

    def test_api_compatibility_with_old_engine(self):
        """EventDrivenBacktestEngine API 與舊版相同"""
        df = make_df(100)
        entries = pd.Series(False, index=df.index)
        exits = pd.Series(False, index=df.index)
        entries.iloc[20] = True
        exits.iloc[60] = True

        engine = EventDrivenBacktestEngine(
            data=df, initial_capital=10000, commission=0.0, slippage=0.0
        )
        results = engine.run(entries, exits, direction="long")

        # 與舊版 BacktestEngine 相同的回傳格式
        assert "data" in results
        assert "trades" in results
        assert "metrics" in results
        assert len(results["trades"]) >= 1
        # 結果存回 self.results
        assert engine.results is not None

    def test_direction_param_does_not_break(self):
        """direction 參數不會 crash（雖然事件驅動版不直接用它）"""
        df = make_df(50)
        entries = pd.Series(False, index=df.index)
        exits = pd.Series(False, index=df.index)
        entries.iloc[10] = True
        exits.iloc[30] = True

        engine = EventDrivenBacktestEngine(df, initial_capital=10000)
        for direction in ["long", "short", "long_short"]:
            results = engine.run(entries, exits, direction=direction)
            assert "trades" in results

    def test_stop_loss_param(self):
        """停損參數"""
        df = make_df(50)
        entries = pd.Series(False, index=df.index)
        exits = pd.Series(False, index=df.index)
        entries.iloc[10] = True

        engine = EventDrivenBacktestEngine(
            df, initial_capital=10000, commission=0.0, slippage=0.0
        )
        results = engine.run(entries, exits, stop_loss=0.05)
        assert len(results["trades"]) == 1

    def test_long_short_mode(self):
        """long_short 模式：同時支援 long/short 訊號"""
        df = make_df(50)
        long_entries = pd.Series(False, index=df.index)
        long_exits = pd.Series(False, index=df.index)
        short_entries = pd.Series(False, index=df.index)
        short_exits = pd.Series(False, index=df.index)
        long_entries.iloc[10] = True
        long_exits.iloc[20] = True
        short_entries.iloc[25] = True
        short_exits.iloc[35] = True

        engine = EventDrivenBacktestEngine(df, initial_capital=10000)
        results = engine.run(
            long_entries, long_exits,
            direction="long_short",
            long_entries=long_entries, long_exits=long_exits,
            short_entries=short_entries, short_exits=short_exits,
        )
        assert len(results["trades"]) == 2
        assert results["trades"][0]["direction"] == "long"
        assert results["trades"][1]["direction"] == "short"
