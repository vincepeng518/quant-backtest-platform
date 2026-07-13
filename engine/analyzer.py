from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from engine.backtester import Backtester
from engine.optimizer import Optimizer
from strategies.base import StrategyBase


class WalkForwardAnalyzer:
    def __init__(self, backtester: Backtester) -> None:
        self.backtester = backtester

    def analyze(
        self,
        data: pd.DataFrame,
        strategy_cls: type[StrategyBase],
        param_space: dict[str, Any],
        n_windows: int = 10,
        is_ratio: float = 0.7,
        opt_method: str = "grid",
    ) -> dict[str, Any]:
        window_size = len(data) // n_windows
        is_size = int(window_size * is_ratio)
        results: list[dict] = []

        for i in range(n_windows):
            end = (i + 1) * window_size
            is_end = i * window_size + is_size
            is_data = data.iloc[i * window_size : is_end]
            oos_data = data.iloc[is_end:end]

            self.backtester.set_data(is_data)
            strat = strategy_cls()
            self.backtester.set_strategy(strat)
            opt = Optimizer(self.backtester, metric="sharpe_ratio")
            opt_results = opt.grid_search(param_space) if opt_method == "grid" else opt.bayesian_optimization(param_space)

            best_params = opt_results[0]["params"]
            is_result = opt_results[0]["result"]
            if is_result is None:
                # all candidate param sets failed to backtest; skip this window
                continue

            self.backtester.set_data(oos_data)
            oos_strat = strategy_cls()
            oos_strat.init(best_params)
            self.backtester.set_strategy(oos_strat)
            oos_result = self.backtester.run()

            results.append(
                {
                    "window": i,
                    "is_sharpe": is_result.sharpe_ratio,
                    "oos_sharpe": oos_result.sharpe_ratio,
                    "is_return": is_result.total_return_pct,
                    "oos_return": oos_result.total_return_pct,
                    "is_max_dd": is_result.max_drawdown_pct,
                    "oos_max_dd": oos_result.max_drawdown_pct,
                    "best_params": best_params,
                    "oos_trades": oos_result.total_trades,
                }
            )

        if not results:
            return {
                "windows": [],
                "avg_oos_sharpe": 0.0,
                "avg_oos_return": 0.0,
                "sharpe_std": 0.0,
                "return_std": 0.0,
                "consistency": 0.0,
            }
        return self._aggregate(results)

    @staticmethod
    def _aggregate(results: list[dict]) -> dict[str, Any]:
        oos_sharpes = [r["oos_sharpe"] for r in results]
        oos_returns = [r["oos_return"] for r in results]
        return {
            "windows": results,
            "avg_oos_sharpe": float(np.mean(oos_sharpes)),
            "avg_oos_return": float(np.mean(oos_returns)),
            "sharpe_std": float(np.std(oos_sharpes)),
            "return_std": float(np.std(oos_returns)),
            "consistency": float(np.sum(np.array(oos_sharpes) > 0) / len(oos_sharpes) * 100),
        }


class MonteCarloSimulator:
    def __init__(self, equity_curve: list[float], n_simulations: int = 1000) -> None:
        self.equity_curve = equity_curve
        self.n_simulations = n_simulations
        arr = np.array(equity_curve)
        self.daily_returns = np.diff(arr) / arr[:-1]

    def simulate(self, initial_capital: float = 100_000, n_days: int = 252) -> dict[str, Any]:
        paths: list[list[float]] = []
        final_values: list[float] = []
        max_drawdowns: list[float] = []

        for _ in range(self.n_simulations):
            sampled = np.random.choice(self.daily_returns, size=n_days, replace=True)
            path = [initial_capital]
            for r in sampled:
                path.append(path[-1] * (1 + r))
            paths.append(path)
            final_values.append(path[-1])
            peak = np.maximum.accumulate(path)
            dd = (peak - np.array(path)) / peak
            max_drawdowns.append(float(np.max(dd) * 100))

        fv = np.array(final_values)
        md = np.array(max_drawdowns)

        return {
            "paths": paths,
            "percentiles": {
                "5": float(np.percentile(fv, 5)),
                "25": float(np.percentile(fv, 25)),
                "50": float(np.percentile(fv, 50)),
                "75": float(np.percentile(fv, 75)),
                "95": float(np.percentile(fv, 95)),
            },
            "final_values": final_values,
            "max_drawdowns": list(md),
            "bankruptcy_prob": float(np.sum(fv < initial_capital * 0.5) / self.n_simulations * 100),
            "expected_return": float(np.mean(fv)),
            "return_std": float(np.std(fv)),
            "var_95": float(np.percentile(fv, 5)),
            "cvar_95": float(np.mean(fv[fv <= np.percentile(fv, 5)])),
        }