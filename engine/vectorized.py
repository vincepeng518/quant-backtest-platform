from __future__ import annotations

import numpy as np
import pandas as pd


class VectorizedBacktester:
    """向量化快速回測 — 用於優化中的快速評估，犧牲精度換速度。"""

    def run(
        self,
        signals: pd.Series,
        prices: pd.Series,
        initial_capital: float = 100_000,
        commission: float = 0.001,
    ) -> dict:
        positions = signals.shift(1).fillna(0)
        returns = prices.pct_change().fillna(0)
        strat_returns = positions * returns
        trade_costs = (signals.diff().fillna(0) != 0).astype(float) * commission
        net = strat_returns - trade_costs

        equity = (1 + net).cumprod() * initial_capital
        peak = equity.expanding().max()
        dd = (equity - peak) / peak

        return {
            "equity_curve": equity.values,
            "returns": net.values,
            "sharpe": self._sharpe(net),
            "total_return": float(equity.iloc[-1] / initial_capital - 1),
            "max_drawdown": float(dd.min()),
        }

    @staticmethod
    def _sharpe(returns: pd.Series, periods: int = 252) -> float:
        if returns.std() == 0:
            return 0.0
        return float(np.sqrt(periods) * returns.mean() / returns.std())