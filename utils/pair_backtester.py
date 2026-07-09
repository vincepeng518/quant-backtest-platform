"""
配對交易回測引擎
支援同時持有兩個反向部位（例如：買 BTC + 空 ETH）

使用方式：
- df 應包含兩個標的的 OHLCV 資料，欄位以 symbol 為前綴
  例如：df['BTC/USDT_close'], df['ETH/USDT_close'], ...
- 策略回傳 (entries, exits) 兩個 bool Series
- 進場時會自動建立配對部位（symbol1 long + symbol2 short）
- 出場時會自動平倉兩個部位
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional


class PairBacktestEngine:
    """
    配對交易回測引擎

    範例：
    engine = PairBacktestEngine(
        df=merged_df,           # 包含兩個標的的 OHLCV
        symbol1='BTC/USDT',     # 做多標的
        symbol2='ETH/USDT',     # 做空標的
        capital_per_leg=0.5,    # 每邊部位佔 50% 資金
        commission=0.001,
        slippage=0.0005,
    )
    results = engine.run(entries, exits, direction='pair_long')
    """

    def __init__(
        self,
        data: pd.DataFrame,
        symbol1: str = "BTC/USDT",
        symbol2: str = "ETH/USDT",
        initial_capital: float = 10000.0,
        capital_per_leg: float = 0.5,  # 每邊部位佔比（總和應 <= 1）
        commission: float = 0.001,
        slippage: float = 0.0005,
    ):
        """
        data: 必須包含兩個標的的 OHLCV 欄位
              欄位命名格式：f"{symbol}_open", f"{symbol}_high", f"{symbol}_low", f"{symbol}_close", f"{symbol}_volume"
        symbol1, symbol2: 兩個交易對名稱
        capital_per_leg: 每邊投入資金比例（0.5 = 各 50%）
        """
        self.data = data.copy()
        self.symbol1 = symbol1
        self.symbol2 = symbol2
        self.initial_capital = initial_capital
        self.capital_per_leg = capital_per_leg
        self.commission = commission
        self.slippage = slippage
        self.results = None

        # 驗證資料欄位
        required_cols = []
        for sym in [symbol1, symbol2]:
            for col in ["open", "high", "low", "close"]:
                required_cols.append(f"{sym}_{col}")

        missing = [c for c in required_cols if c not in data.columns]
        if missing:
            raise ValueError(
                f"資料缺少必要欄位: {missing}\n"
                f"需要欄位格式: {symbol1}_open, {symbol1}_high, {symbol1}_low, {symbol1}_close, "
                f"{symbol2}_open, {symbol2}_high, {symbol2}_low, {symbol2}_close"
            )

    def run(
        self,
        entries: pd.Series,
        exits: pd.Series,
        direction: str = "pair_long",  # pair_long=做多比率, pair_short=做空比率
        stop_loss: float = None,        # 比率層級停損（可選）
        take_profit: float = None,      # 比率層級停利（可選）
    ) -> Dict:
        """
        執行配對交易回測
        direction: "pair_long" = 買 symbol1 + 空 symbol2
                   "pair_short" = 空 symbol1 + 買 symbol2
        """
        df = self.data.copy()
        df["entry"] = entries.astype(bool).fillna(False)
        df["exit"] = exits.astype(bool).fillna(False)

        # 產生配對交易序列
        positions, trades = self._generate_pair_trades(df, direction, stop_loss, take_profit)

        df["position"] = positions
        df[f"{self.symbol1}_pos"] = positions * self.capital_per_leg
        df[f"{self.symbol2}_pos"] = -positions * self.capital_per_leg

        # 計算權益曲線
        df = self._calculate_pair_equity(df)

        # 計算績效指標
        metrics = self._calculate_metrics(df, trades)

        self.results = {
            "data": df,
            "trades": trades,
            "metrics": metrics,
        }
        return self.results

    def _generate_pair_trades(
        self, df: pd.DataFrame, direction: str, stop_loss: float, take_profit: float
    ) -> Tuple[pd.Series, List[Dict]]:
        """產生配對交易序列"""
        position = pd.Series(0, index=df.index)
        trades = []

        current_pos = 0  # 0=空手, 1=做多比率, -1=做空比率
        entry_ratio = 0.0
        entry_time = None
        entry_p1 = 0.0  # symbol1 進場價
        entry_p2 = 0.0  # symbol2 進場價

        sym1_close = df[f"{self.symbol1}_close"].values
        sym2_close = df[f"{self.symbol2}_close"].values
        sym1_low = df[f"{self.symbol1}_low"].values
        sym1_high = df[f"{self.symbol1}_high"].values
        sym2_low = df[f"{self.symbol2}_low"].values
        sym2_high = df[f"{self.symbol2}_high"].values

        for i in range(len(df)):
            timestamp = df.index[i]
            p1 = sym1_close[i]
            p2 = sym2_close[i]
            ratio = p1 / p2 if p2 > 0 else 0

            # 檢查停損/停利（基於比率變化）
            if current_pos != 0 and (stop_loss is not None or take_profit is not None):
                if current_pos == 1:  # 做多比率（symbol1 漲或 symbol2 跌 → 比率上升）
                    pnl_ratio = (ratio - entry_ratio) / entry_ratio
                else:  # 做空比率
                    pnl_ratio = (entry_ratio - ratio) / entry_ratio

                exit_triggered = False
                exit_reason = ""

                if take_profit is not None and pnl_ratio >= take_profit:
                    exit_triggered = True
                    exit_reason = "take_profit"
                elif stop_loss is not None and pnl_ratio <= -stop_loss:
                    exit_triggered = True
                    exit_reason = "stop_loss"

                if exit_triggered:
                    # 平倉兩個部位
                    if current_pos == 1:
                        # 買 symbol1 + 空 symbol2
                        exit_p1 = sym1_high[i] if exit_reason == "take_profit" else sym1_low[i]
                        exit_p2 = sym2_low[i] if exit_reason == "take_profit" else sym2_high[i]
                    else:
                        # 空 symbol1 + 買 symbol2
                        exit_p1 = sym1_low[i] if exit_reason == "take_profit" else sym1_high[i]
                        exit_p2 = sym2_high[i] if exit_reason == "take_profit" else sym2_low[i]

                    # 計算損益
                    if current_pos == 1:
                        # 部位 1: long symbol1, 部位 2: short symbol2
                        pnl1 = (exit_p1 - entry_p1) / entry_p1
                        pnl2 = (entry_p2 - exit_p2) / entry_p2
                    else:
                        # 部位 1: short symbol1, 部位 2: long symbol2
                        pnl1 = (entry_p1 - exit_p1) / entry_p1
                        pnl2 = (exit_p2 - entry_p2) / entry_p2

                    # 扣除手續費（兩個邊各收一次）
                    pnl_pct = (pnl1 + pnl2) / 2 - 2 * self.commission

                    trades.append({
                        "entry_time": entry_time,
                        "exit_time": timestamp,
                        "direction": "pair_long" if current_pos == 1 else "pair_short",
                        "entry_p1": entry_p1,
                        "entry_p2": entry_p2,
                        "exit_p1": exit_p1,
                        "exit_p2": exit_p2,
                        "entry_ratio": entry_ratio,
                        "exit_ratio": ratio,
                        "pnl1_pct": pnl1 * 100,
                        "pnl2_pct": pnl2 * 100,
                        "pnl_pct": pnl_pct * 100,
                        "pnl": pnl_pct * self.initial_capital,
                        "duration_hours": (timestamp - entry_time).total_seconds() / 3600,
                        "exit_reason": exit_reason,
                    })
                    current_pos = 0
                    entry_ratio = 0.0

            # 處理進場訊號
            if df["entry"].iloc[i] and current_pos == 0:
                # 進場時買入兩個標的
                if direction == "pair_long":
                    # 做多比率：買 symbol1, 空 symbol2
                    current_pos = 1
                else:
                    # 做空比率：空 symbol1, 買 symbol2
                    current_pos = -1

                # 計算進場價（含滑點）
                if current_pos == 1:
                    entry_p1 = p1 * (1 + self.slippage)  # 買入
                    entry_p2 = p2 * (1 - self.slippage)  # 放空
                else:
                    entry_p1 = p1 * (1 - self.slippage)  # 放空
                    entry_p2 = p2 * (1 + self.slippage)  # 買入

                entry_ratio = entry_p1 / entry_p2 if entry_p2 > 0 else 0
                entry_time = timestamp

            # 處理出場訊號
            elif df["exit"].iloc[i] and current_pos != 0:
                # 平倉兩個部位
                if current_pos == 1:
                    exit_p1 = p1 * (1 - self.slippage)  # 賣出
                    exit_p2 = p2 * (1 + self.slippage)  # 買回
                    pnl1 = (exit_p1 - entry_p1) / entry_p1
                    pnl2 = (entry_p2 - exit_p2) / entry_p2
                else:
                    exit_p1 = p1 * (1 + self.slippage)  # 買回
                    exit_p2 = p2 * (1 - self.slippage)  # 賣出
                    pnl1 = (entry_p1 - exit_p1) / entry_p1
                    pnl2 = (exit_p2 - entry_p2) / entry_p2

                pnl_pct = (pnl1 + pnl2) / 2 - 2 * self.commission

                trades.append({
                    "entry_time": entry_time,
                    "exit_time": timestamp,
                    "direction": "pair_long" if current_pos == 1 else "pair_short",
                    "entry_p1": entry_p1,
                    "entry_p2": entry_p2,
                    "exit_p1": exit_p1,
                    "exit_p2": exit_p2,
                    "entry_ratio": entry_ratio,
                    "exit_ratio": ratio,
                    "pnl1_pct": pnl1 * 100,
                    "pnl2_pct": pnl2 * 100,
                    "pnl_pct": pnl_pct * 100,
                    "pnl": pnl_pct * self.initial_capital,
                    "duration_hours": (timestamp - entry_time).total_seconds() / 3600,
                    "exit_reason": "signal",
                })
                current_pos = 0
                entry_ratio = 0.0

            position.iloc[i] = current_pos

        # 若最後仍持倉，強制平倉
        if current_pos != 0:
            last_p1 = sym1_close[-1]
            last_p2 = sym2_close[-1]
            if current_pos == 1:
                exit_p1 = last_p1 * (1 - self.slippage)
                exit_p2 = last_p2 * (1 + self.slippage)
                pnl1 = (exit_p1 - entry_p1) / entry_p1
                pnl2 = (entry_p2 - exit_p2) / entry_p2
            else:
                exit_p1 = last_p1 * (1 + self.slippage)
                exit_p2 = last_p2 * (1 - self.slippage)
                pnl1 = (entry_p1 - exit_p1) / entry_p1
                pnl2 = (exit_p2 - entry_p2) / entry_p2

            pnl_pct = (pnl1 + pnl2) / 2 - 2 * self.commission

            trades.append({
                "entry_time": entry_time,
                "exit_time": df.index[-1],
                "direction": "pair_long" if current_pos == 1 else "pair_short",
                "entry_p1": entry_p1,
                "entry_p2": entry_p2,
                "exit_p1": exit_p1,
                "exit_p2": exit_p2,
                "entry_ratio": entry_ratio,
                "exit_ratio": last_p1 / last_p2,
                "pnl1_pct": pnl1 * 100,
                "pnl2_pct": pnl2 * 100,
                "pnl_pct": pnl_pct * 100,
                "pnl": pnl_pct * self.initial_capital,
                "duration_hours": (df.index[-1] - entry_time).total_seconds() / 3600,
                "exit_reason": "end",
            })

        return position, trades

    def _calculate_pair_equity(self, df: pd.DataFrame) -> pd.DataFrame:
        """計算配對交易的權益曲線"""
        # 計算兩個標的的報酬
        df[f"{self.symbol1}_returns"] = df[f"{self.symbol1}_close"].pct_change().fillna(0)
        df[f"{self.symbol2}_returns"] = df[f"{self.symbol2}_close"].pct_change().fillna(0)

        # 部位報酬（延遲一檔）
        pos1 = df[f"{self.symbol1}_pos"].shift(1).fillna(0)  # symbol1 部位
        pos2 = df[f"{self.symbol2}_pos"].shift(1).fillna(0)  # symbol2 部位

        # 策略報酬 = symbol1 部位報酬 + symbol2 部位報酬
        df["strategy_returns"] = (
            pos1 * df[f"{self.symbol1}_returns"]
            + pos2 * df[f"{self.symbol2}_returns"]
        )

        # 權益曲線
        df["equity"] = self.initial_capital * (1 + df["strategy_returns"]).cumprod()

        # 買進持有（symbol1 買進持有當作對比）
        df["buy_hold"] = self.initial_capital * (1 + df[f"{self.symbol1}_returns"]).cumprod()

        # 比率序列
        df["ratio"] = df[f"{self.symbol1}_close"] / df[f"{self.symbol2}_close"]

        return df

    def _calculate_metrics(self, df: pd.DataFrame, trades: List[Dict]) -> Dict:
        """計算配對交易績效指標"""
        if len(trades) == 0:
            return {"error": "無交易"}

        trades_df = pd.DataFrame(trades)
        equity = df["equity"]
        returns = df["strategy_returns"]

        n_trades = len(trades_df)
        winners = trades_df[trades_df["pnl"] > 0]
        losers = trades_df[trades_df["pnl"] <= 0]
        win_rate = len(winners) / n_trades if n_trades > 0 else 0

        avg_win = winners["pnl_pct"].mean() if len(winners) > 0 else 0
        avg_loss = losers["pnl_pct"].mean() if len(losers) > 0 else 0
        profit_factor = (
            abs(winners["pnl"].sum() / losers["pnl"].sum())
            if len(losers) > 0 and losers["pnl"].sum() != 0
            else np.inf
        )

        total_return = (equity.iloc[-1] / self.initial_capital - 1) * 100
        buy_hold_return = (df["buy_hold"].iloc[-1] / self.initial_capital - 1) * 100

        cummax = equity.cummax()
        drawdown = (equity - cummax) / cummax
        max_drawdown = drawdown.min() * 100

        if returns.std() > 0:
            freq = self._infer_frequency(df)
            sharpe = (returns.mean() / returns.std()) * np.sqrt(freq)
        else:
            sharpe = 0

        avg_duration = trades_df["duration_hours"].mean()

        return {
            "n_trades": n_trades,
            "win_rate": win_rate * 100,
            "avg_win_pct": avg_win,
            "avg_loss_pct": avg_loss,
            "profit_factor": profit_factor,
            "total_return_pct": total_return,
            "buy_hold_return_pct": buy_hold_return,
            "max_drawdown_pct": max_drawdown,
            "sharpe_ratio": sharpe,
            "final_equity": equity.iloc[-1],
            "avg_duration_hours": avg_duration,
            "long_trades": len(trades_df[trades_df["direction"] == "pair_long"]),
            "short_trades": len(trades_df[trades_df["direction"] == "pair_short"]),
            "is_pair_trading": True,
            "symbol1": self.symbol1,
            "symbol2": self.symbol2,
        }

    def _infer_frequency(self, df: pd.DataFrame) -> int:
        """推斷資料頻率"""
        if len(df) < 2:
            return 252
        median_diff = df.index.to_series().diff().median()
        seconds = median_diff.total_seconds()

        if seconds <= 60:
            return 60 * 24 * 365
        elif seconds <= 300:
            return 12 * 24 * 365
        elif seconds <= 900:
            return 4 * 24 * 365
        elif seconds <= 3600:
            return 24 * 365
        elif seconds <= 86400:
            return 252
        elif seconds <= 604800:
            return 52
        else:
            return 12
