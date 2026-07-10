"""
事件驅動回測引擎 - 對外公開介面

提供與舊版 BacktestEngine 完全相容的 API，
內部用 EventEngine 執行（事件驅動架構）。

舊版調用：
    engine = BacktestEngine(df, capital, commission, slippage)
    results = engine.run(entries, exits, direction=..., stop_loss=...)

新版完全相容：
    engine = EventDrivenBacktestEngine(df, capital, commission, slippage)
    results = engine.run(entries, exits, direction=..., stop_loss=...)
"""
from __future__ import annotations

from typing import Optional
import pandas as pd

from engine import EventEngine
from events import BarEvent
from handlers.strategy_handler import StrategyHandler


class EventDrivenBacktestEngine:
    """
    事件驅動回測引擎（API 100% 相容舊版 BacktestEngine）

    內部流程：
    1. 把 entries/exits 預算 series 灌入 StrategyHandler
    2. 逐根 K 線產生 BarEvent
    3. EventEngine 串接 Strategy → RiskManager → Execution → Portfolio
    4. 最後一根 K 線時，若有持倉則平倉
    5. 收集 trades + equity_curve，構造與舊版相同格式的 dict
    """

    def __init__(
        self,
        data: pd.DataFrame,
        initial_capital: float = 10000.0,
        commission: float = 0.001,
        slippage: float = 0.0005,
    ):
        self.data = data.copy()
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.results = None

    def run(
        self,
        entries: pd.Series,
        exits: pd.Series,
        direction: str = "long",
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        long_entries: Optional[pd.Series] = None,
        long_exits: Optional[pd.Series] = None,
        short_entries: Optional[pd.Series] = None,
        short_exits: Optional[pd.Series] = None,
    ) -> dict:
        """
        執行事件驅動回測

        Returns:
            dict with keys: "data", "trades", "metrics"
        """
        # 建立 EventEngine
        engine = EventEngine(
            initial_capital=self.initial_capital,
            commission=self.commission,
            slippage=self.slippage,
            max_position_pct=1.0,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        # 設定預算 signals
        engine.set_precomputed_signals(
            entries, exits, long_entries, long_exits, short_entries, short_exits
        )

        # 逐根 K 線跑
        for timestamp, row in self.data.iterrows():
            bar = BarEvent.from_row(timestamp, row)
            engine._queue.append(bar)
            # 設定 SLTP（如果啟用）
            if stop_loss or take_profit:
                from events import OrderSide
                pos = engine.portfolio.get_position()
                if pos != 0 and engine.portfolio.entry_time is not None:
                    side = OrderSide.BUY if pos == 1 else OrderSide.SELL
                    sl_price = (
                        engine.portfolio.entry_price * (1 - stop_loss)
                        if pos == 1
                        else engine.portfolio.entry_price * (1 + stop_loss)
                    )
                    tp_price = (
                        engine.portfolio.entry_price * (1 + take_profit)
                        if pos == 1
                        else engine.portfolio.entry_price * (1 - take_profit)
                    )
                    engine.sltp.set_position(
                        side,
                        engine.portfolio.entry_price,
                        sl_price if stop_loss else None,
                        tp_price if take_profit else None,
                    )
                else:
                    engine.sltp.clear()

            # 處理 queue 中所有事件
            while engine._queue:
                ev = engine._queue.popleft()
                engine._dispatch(ev)
            # 同步 RiskManager 持倉
            engine.risk.update_position(engine.portfolio.position)
            # 記錄權益
            engine.portfolio.snapshot_equity(timestamp)

        # 最後一根 K 線收盤時，若有持倉則平倉
        if engine.portfolio.position != 0:
            from events import FillEvent, OrderEvent, OrderSide, OrderType
            close_side = OrderSide.SELL if engine.portfolio.position == 1 else OrderSide.BUY
            order = OrderEvent(
                timestamp=self.data.index[-1],
                side=close_side,
                order_type=OrderType.MARKET,
                quantity=1.0,
                price=float(self.data["close"].iloc[-1]),
                is_close=True,
            )
            engine._dispatch(order)
            # 處理後續 FillEvent 等事件
            while engine._queue:
                ev = engine._queue.popleft()
                engine._dispatch(ev)
            engine.risk.update_position(engine.portfolio.position)

        # 構造與舊版相容的結果
        results = {
            "data": engine.portfolio.build_equity_dataframe(),
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
                for t in engine.portfolio.trades
            ],
            "metrics": engine.portfolio.calculate_metrics(),
        }
        self.results = results
        return results
