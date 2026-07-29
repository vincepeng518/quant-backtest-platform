from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from engine.backtester import Backtester
from engine.optimizer import Optimizer
from strategies.base import StrategyBase


def _optimize_params(
    is_df: pd.DataFrame,
    strategy_cls: type[StrategyBase],
    param_space: dict[str, Any],
    fallback: dict,
) -> dict:
    """Lightweight Bayesian opt on IS data. Returns fallback on failure."""
    bt = Backtester()
    bt.set_data(is_df)
    s = strategy_cls()
    bt.set_strategy(s)
    opt = Optimizer(bt, metric="sharpe_ratio", maximize=True)
    try:
        res = opt.bayesian_optimization(param_space, n_iterations=8, n_initial=6)
        params = res[0]["params"]
        return params if params else fallback
    except Exception:
        return fallback


class WalkForwardAnalyzer:
    """True Walk-Forward: each OOS window is optimised on *preceding* IS data.

    Mirrors the proven logic in research/optimize_local.py::_walk_forward_oos.
    """

    def __init__(self, backtester: Backtester) -> None:
        self.backtester = backtester

    def analyze(
        self,
        data: pd.DataFrame,
        strategy_cls: type[StrategyBase],
        param_space: dict[str, Any],
        n_windows: int = 3,
        is_ratio: float = 0.0,  # unused — kept for backward compat
        opt_method: str = "bayesian",  # unused — kept for backward compat
    ) -> dict[str, Any]:
        n = len(data)
        win = n // n_windows
        MIN_IS = 300

        if win < 50:
            # Too little data: single IS/OOS split
            half = n // 2
            is_df = data.iloc[:half]
            oos_df = data.iloc[half:]
            best_i = _optimize_params(is_df, strategy_cls, param_space, {})
            return self._eval_oos([(is_df, oos_df, best_i, False)], strategy_cls)

        # Full best params on whole dataset (fallback for short IS windows)
        bt = Backtester()
        bt.set_data(data)
        s = strategy_cls()
        bt.set_strategy(s)
        opt = Optimizer(bt, metric="sharpe_ratio", maximize=True)
        try:
            full_res = opt.bayesian_optimization(param_space, n_iterations=15, n_initial=10)
            full_best = full_res[0]["params"]
        except Exception:
            full_best = {}

        oos_sharpes, oos_returns, oos_dds = [], [], []
        windows = []
        prev_best = full_best

        for i in range(1, n_windows):
            is_df = data.iloc[: i * win]
            oos_df = data.iloc[i * win : (i + 1) * win]
            if len(is_df) < 30 or len(oos_df) < 5:
                continue
            if len(is_df) < MIN_IS:
                best_i = prev_best
                used_fb = True
            else:
                best_i = _optimize_params(is_df, strategy_cls, param_space, prev_best)
                used_fb = not best_i
                if used_fb:
                    best_i = prev_best
            prev_best = best_i

            bt2 = Backtester()
            bt2.set_data(oos_df)
            s2 = strategy_cls()
            s2.init(best_i)
            bt2.set_strategy(s2)
            try:
                r = bt2.run()
                oos_sharpes.append(r.sharpe_ratio)
                oos_returns.append(r.total_return_pct)
                oos_dds.append(r.max_drawdown_pct)
                windows.append({
                    "is_range": f"0..{i * win}",
                    "oos_range": f"{i * win}..{(i + 1) * win}",
                    "oos_sharpe": r.sharpe_ratio,
                    "oos_return": r.total_return_pct,
                    "oos_max_dd": r.max_drawdown_pct,
                    "used_fallback": used_fb,
                })
            except Exception:
                continue

        if not oos_sharpes:
            return {
                "windows": [],
                "avg_oos_sharpe": 0.0,
                "avg_oos_return": 0.0,
                "sharpe_std": 0.0,
                "return_std": 0.0,
                "consistency": 0.0,
            }
        return self._aggregate(oos_sharpes, oos_returns, windows)

    @staticmethod
    def _eval_oos(
        pairs: list[tuple[pd.DataFrame, pd.DataFrame, dict, bool]],
        strategy_cls: type[StrategyBase],
    ) -> dict:
        oos_sharpes, oos_returns, oos_dds, windows = [], [], [], []
        for is_df, oos_df, best_i, used_fb in pairs:
            bt = Backtester()
            bt.set_data(oos_df)
            s = strategy_cls()
            s.init(best_i)
            bt.set_strategy(s)
            try:
                r = bt.run()
                oos_sharpes.append(r.sharpe_ratio)
                oos_returns.append(r.total_return_pct)
                oos_dds.append(r.max_drawdown_pct)
                windows.append({
                    "oos_sharpe": r.sharpe_ratio,
                    "oos_return": r.total_return_pct,
                    "oos_max_dd": r.max_drawdown_pct,
                    "used_fallback": used_fb,
                })
            except Exception:
                continue
        if not oos_sharpes:
            return {
                "windows": [],
                "avg_oos_sharpe": 0.0,
                "avg_oos_return": 0.0,
                "sharpe_std": 0.0,
                "return_std": 0.0,
                "consistency": 0.0,
            }
        arr = np.array(oos_sharpes)
        return {
            "avg_oos_sharpe": float(arr.mean()),
            "avg_oos_return": float(np.mean(oos_returns)),
            "sharpe_std": float(arr.std()),
            "return_std": float(np.std(oos_returns)),
            "consistency": float((arr > 0).sum() / len(arr)),
            "windows": windows,
        }

    @staticmethod
    def _aggregate(oos_sharpes: list, oos_returns: list, windows: list) -> dict:
        arr = np.array(oos_sharpes)
        return {
            "windows": windows,
            "avg_oos_sharpe": float(arr.mean()),
            "avg_oos_return": float(np.mean(oos_returns)),
            "sharpe_std": float(arr.std()),
            "return_std": float(np.std(oos_returns)),
            "consistency": float((arr > 0).sum() / len(arr) * 100),
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