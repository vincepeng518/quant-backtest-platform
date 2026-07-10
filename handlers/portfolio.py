"""
Portfolio handler：接收 FillEvent 與 BarEvent，維護持倉/餘額/權益

計算：
- 當前持倉
- 現金餘額
- 總權益（mark-to-market）
- 交易記錄
- 績效指標
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List
import numpy as np
import pandas as pd

from events import BarEvent, Event, FillEvent, OrderSide, OrderType
from handlers import EventHandler


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    direction: str  # "long" or "short"
    entry_price: float
    exit_price: float
    pnl_pct: float
    pnl: float
    duration_hours: float
    exit_reason: str = ""


class PortfolioHandler(EventHandler):
    """
    投資組合管理

    設計：
    - position ∈ {-1, 0, 1}：-1=空, 0=無, 1=多
    - 收到 BarEvent：更新 mark-to-market 權益
    - 收到 FillEvent：更新持倉、現金、記錄 trade
    """

    def __init__(self, initial_capital: float = 10000.0, commission: float = 0.001):
        self.initial_capital = initial_capital
        self.commission = commission
        self.cash = initial_capital
        self.position = 0
        self.entry_price = 0.0
        self.entry_time = None
        self.current_bar = None
        self.current_price = 0.0

        # 輸出
        self.equity_curve: List[Dict] = []
        self.trades: List[Trade] = []

    def update_position_callback(self, position: int) -> None:
        """由外部（RiskManager）呼叫以同步當前倉位"""
        self.position = position

    def get_position(self) -> int:
        return self.position

    def get_equity(self) -> float:
        return self.cash + self.position * self.current_price

    def handle(self, event: Event) -> List[Event]:
        if isinstance(event, BarEvent):
            self.current_bar = event
            self.current_price = event.close
            return []

        if not isinstance(event, FillEvent):
            return []

        # 處理成交
        if event.side == OrderSide.BUY:
            # 買入：可能是開倉或平空
            if self.position == -1:
                # 平空倉
                pnl = (self.entry_price - event.price) * abs(self.position) * self.initial_capital / self.entry_price
                pnl_pct = (self.entry_price - event.price) / self.entry_price - 2 * self.commission
                self._close_trade(event, "short", pnl, pnl_pct, "signal")
            # 開多倉（只有 is_close=False 才是新倉單）
            if not event.is_close:
                self.position = 1
                self.entry_price = event.price
                self.entry_time = event.timestamp
                self.cash -= event.commission

        elif event.side == OrderSide.SELL:
            if self.position == 1:
                # 平多倉
                pnl = (event.price - self.entry_price) * self.initial_capital / self.entry_price
                pnl_pct = (event.price - self.entry_price) / self.entry_price - 2 * self.commission
                self._close_trade(event, "long", pnl, pnl_pct, "signal")
            # 開空倉（只有 is_close=False 才是新倉單）
            if not event.is_close and self.position == 0:
                self.position = -1
                self.entry_price = event.price
                self.entry_time = event.timestamp
                self.cash -= event.commission

        return []

    def _close_trade(self, event: FillEvent, direction: str, pnl: float, pnl_pct: float, reason: str):
        duration = (event.timestamp - self.entry_time).total_seconds() / 3600
        self.trades.append(Trade(
            entry_time=self.entry_time,
            exit_time=event.timestamp,
            direction=direction,
            entry_price=self.entry_price,
            exit_price=event.price,
            pnl_pct=pnl_pct,
            pnl=pnl,
            duration_hours=duration,
            exit_reason=reason,
        ))
        self.cash += pnl
        self.position = 0
        self.entry_price = 0.0
        self.entry_time = None

    def snapshot_equity(self, timestamp) -> None:
        """記錄當前權益到 equity_curve"""
        self.equity_curve.append({
            "timestamp": timestamp,
            "equity": self.get_equity(),
            "position": self.position,
            "price": self.current_price,
        })

    def calculate_metrics(self) -> Dict:
        """計算績效指標"""
        if not self.equity_curve:
            return {"error": "無資料"}
        equity_df = pd.DataFrame(self.equity_curve).set_index("timestamp")
        final_equity = equity_df["equity"].iloc[-1]
        total_return = (final_equity / self.initial_capital - 1) * 100

        n_trades = len(self.trades)
        if n_trades == 0:
            return {"error": "無交易"}

        winners = [t for t in self.trades if t.pnl > 0]
        losers = [t for t in self.trades if t.pnl <= 0]
        win_rate = len(winners) / n_trades * 100

        # 最大回撤
        cummax = equity_df["equity"].cummax()
        drawdown = (equity_df["equity"] - cummax) / cummax
        max_dd = drawdown.min() * 100

        # Sharpe
        returns = equity_df["equity"].pct_change().fillna(0)
        if returns.std() > 0:
            sharpe = (returns.mean() / returns.std()) * np.sqrt(252)
        else:
            sharpe = 0

        return {
            "n_trades": n_trades,
            "win_rate": win_rate,
            "total_return_pct": total_return,
            "max_drawdown_pct": max_dd,
            "sharpe_ratio": sharpe,
            "final_equity": final_equity,
            "long_trades": sum(1 for t in self.trades if t.direction == "long"),
            "short_trades": sum(1 for t in self.trades if t.direction == "short"),
        }

    def build_equity_dataframe(self) -> pd.DataFrame:
        """把 equity_curve 轉成 DataFrame（與舊版相容）"""
        if not self.equity_curve:
            return pd.DataFrame()
        return pd.DataFrame(self.equity_curve).set_index("timestamp")
