"""
回測引擎核心
Vectorized backtesting using pandas/numpy
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple


class BacktestEngine:
    """
    簡化版向量化回測引擎
    - 支援多空（long/short）
    - 支援停損停利
    - 計算完整績效指標
    """

    def __init__(
        self,
        data: pd.DataFrame,
        initial_capital: float = 10000.0,
        commission: float = 0.001,  # 0.1% per trade
        slippage: float = 0.0005,   # 0.05% slippage
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
        direction: str = "long",  # "long" or "short"
        stop_loss: float = None,
        take_profit: float = None,
    ) -> Dict:
        """
        執行回測
        entries: bool Series (True 時進場)
        exits: bool Series (True 時出場)
        """
        df = self.data.copy()
        df["entry"] = entries.astype(bool).fillna(False)
        df["exit"] = exits.astype(bool).fillna(False)

        # 產生進出場訊號序列
        position, trades = self._generate_trades(df, direction, stop_loss, take_profit)
        df["position"] = position

        # 計算權益曲線
        df = self._calculate_equity(df, direction)

        # 計算績效指標
        metrics = self._calculate_metrics(df, trades)

        self.results = {
            "data": df,
            "trades": trades,
            "metrics": metrics,
        }
        return self.results

    def _generate_trades(
        self, df: pd.DataFrame, direction: str, stop_loss: float, take_profit: float
    ) -> Tuple[pd.Series, list]:
        """產生交易序列"""
        position = pd.Series(0, index=df.index)
        trades = []
        current_pos = 0  # 0=flat, 1=long, -1=short
        entry_price = 0.0
        entry_time = None

        for i, (timestamp, row) in enumerate(df.iterrows()):
            price = row["close"]

            # 檢查停損停利（持倉中）
            if current_pos != 0 and stop_loss is not None:
                if current_pos == 1:  # long
                    sl_price = entry_price * (1 - stop_loss)
                    if row["low"] <= sl_price:
                        exit_price = sl_price * (1 - self.slippage)
                        trades.append(
                            self._make_trade(entry_time, timestamp, entry_price, exit_price, current_pos, "stop_loss")
                        )
                        current_pos = 0
                elif current_pos == -1:  # short
                    sl_price = entry_price * (1 + stop_loss)
                    if row["high"] >= sl_price:
                        exit_price = sl_price * (1 + self.slippage)
                        trades.append(
                            self._make_trade(entry_time, timestamp, entry_price, exit_price, current_pos, "stop_loss")
                        )
                        current_pos = 0

            if current_pos != 0 and take_profit is not None:
                if current_pos == 1:  # long
                    tp_price = entry_price * (1 + take_profit)
                    if row["high"] >= tp_price:
                        exit_price = tp_price * (1 - self.slippage)
                        trades.append(
                            self._make_trade(entry_time, timestamp, entry_price, exit_price, current_pos, "take_profit")
                        )
                        current_pos = 0
                elif current_pos == -1:  # short
                    tp_price = entry_price * (1 - take_profit)
                    if row["low"] <= tp_price:
                        exit_price = tp_price * (1 + self.slippage)
                        trades.append(
                            self._make_trade(entry_time, timestamp, entry_price, exit_price, current_pos, "take_profit")
                        )
                        current_pos = 0

            # 處理進場訊號
            if row["entry"] and current_pos == 0:
                if direction == "long":
                    current_pos = 1
                    entry_price = price * (1 + self.slippage)
                else:
                    current_pos = -1
                    entry_price = price * (1 - self.slippage)
                entry_time = timestamp

            # 處理出場訊號
            elif row["exit"] and current_pos != 0:
                if current_pos == 1:
                    exit_price = price * (1 - self.slippage)
                else:
                    exit_price = price * (1 + self.slippage)
                trades.append(
                    self._make_trade(entry_time, timestamp, entry_price, exit_price, current_pos, "signal")
                )
                current_pos = 0

            position.iloc[i] = current_pos

        # 若最後仍持倉，在最後一根 K 線平倉
        if current_pos != 0 and entry_time is not None:
            last_price = df["close"].iloc[-1]
            if current_pos == 1:
                exit_price = last_price * (1 - self.slippage)
            else:
                exit_price = last_price * (1 + self.slippage)
            trades.append(
                self._make_trade(entry_time, df.index[-1], entry_price, exit_price, current_pos, "end")
            )

        return position, trades

    def _make_trade(self, entry_time, exit_time, entry_price, exit_price, direction, reason):
        """建立交易記錄"""
        if direction == 1:  # long
            pnl_pct = (exit_price - entry_price) / entry_price - 2 * self.commission
        else:  # short
            pnl_pct = (entry_price - exit_price) / entry_price - 2 * self.commission

        pnl = pnl_pct * self.initial_capital
        duration = (exit_time - entry_time).total_seconds() / 3600  # hours

        return {
            "entry_time": entry_time,
            "exit_time": exit_time,
            "direction": "long" if direction == 1 else "short",
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl_pct": pnl_pct,
            "pnl": pnl,
            "duration_hours": duration,
            "exit_reason": reason,
        }

    def _calculate_equity(self, df: pd.DataFrame, direction: str) -> pd.DataFrame:
        """計算權益曲線"""
        df["returns"] = df["close"].pct_change().fillna(0)

        # 簡化版：用部位 × 該根 K 線的收益
        # 持倉部位使用「延遲一檔」進場：第 i 根進場 → 第 i+1 根開始才有部位收益
        if direction == "long":
            strategy_returns = df["position"].shift(1).fillna(0) * df["returns"]
        else:  # short
            strategy_returns = -df["position"].shift(1).fillna(0) * df["returns"]

        df["strategy_returns"] = strategy_returns
        df["equity"] = self.initial_capital * (1 + strategy_returns).cumprod()
        df["buy_hold"] = self.initial_capital * (1 + df["returns"]).cumprod()
        return df

    def _calculate_metrics(self, df: pd.DataFrame, trades: list) -> Dict:
        """計算績效指標"""
        if len(trades) == 0:
            return {"error": "無交易"}

        trades_df = pd.DataFrame(trades)
        equity = df["equity"]
        returns = df["strategy_returns"]

        # 交易統計
        n_trades = len(trades_df)
        winners = trades_df[trades_df["pnl"] > 0]
        losers = trades_df[trades_df["pnl"] <= 0]
        win_rate = len(winners) / n_trades if n_trades > 0 else 0

        avg_win = winners["pnl_pct"].mean() if len(winners) > 0 else 0
        avg_loss = losers["pnl_pct"].mean() if len(losers) > 0 else 0
        profit_factor = (
            abs(winners["pnl"].sum() / losers["pnl"].sum()) if len(losers) > 0 and losers["pnl"].sum() != 0 else np.inf
        )

        # 權益曲線統計
        total_return = (equity.iloc[-1] / self.initial_capital - 1) * 100
        buy_hold_return = (df["buy_hold"].iloc[-1] / self.initial_capital - 1) * 100

        # 最大回撤
        cummax = equity.cummax()
        drawdown = (equity - cummax) / cummax
        max_drawdown = drawdown.min() * 100

        # Sharpe Ratio (年化，假設 252 交易日或 365*24 小時線)
        if returns.std() > 0:
            # 估算年化週期：如果是日線用 252，小時線用 252*24，等等
            freq = self._infer_frequency(df)
            sharpe = (returns.mean() / returns.std()) * np.sqrt(freq)
        else:
            sharpe = 0

        # 平均持倉時間
        avg_duration = trades_df["duration_hours"].mean()

        return {
            "n_trades": n_trades,
            "win_rate": win_rate * 100,
            "avg_win_pct": avg_win * 100,
            "avg_loss_pct": avg_loss * 100,
            "profit_factor": profit_factor,
            "total_return_pct": total_return,
            "buy_hold_return_pct": buy_hold_return,
            "max_drawdown_pct": max_drawdown,
            "sharpe_ratio": sharpe,
            "final_equity": equity.iloc[-1],
            "avg_duration_hours": avg_duration,
            "long_trades": len(trades_df[trades_df["direction"] == "long"]),
            "short_trades": len(trades_df[trades_df["direction"] == "short"]),
        }

    def _infer_frequency(self, df: pd.DataFrame) -> int:
        """推斷資料頻率以年化 Sharpe"""
        if len(df) < 2:
            return 252
        median_diff = df.index.to_series().diff().median()
        seconds = median_diff.total_seconds()

        if seconds <= 60:        # 1 分鐘
            return 60 * 24 * 365
        elif seconds <= 300:      # 5 分鐘
            return 12 * 24 * 365
        elif seconds <= 900:      # 15 分鐘
            return 4 * 24 * 365
        elif seconds <= 3600:     # 1 小時
            return 24 * 365
        elif seconds <= 86400:    # 1 日
            return 252
        elif seconds <= 604800:   # 1 週
            return 52
        else:
            return 12
