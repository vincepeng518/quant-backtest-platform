"""
參數擾動測試（Perturbation Test）

在最佳參數附近做微小擾動，測試策略的穩健性：
1. 對每個參數做 ±X% 擾動
2. 重新跑回測
3. 統計指標的變異（CV、信心區間）

若最佳參數是「參數平原」（附近表現接近）→ 穩健
若最佳參數是「尖峰」（附近表現急劇下降）→ 過擬合風險
"""
from __future__ import annotations

import time
from typing import Dict, List, Any, Optional, Callable
import numpy as np
import pandas as pd


class PerturbationTester:
    """
    擾動測試器

    範例:
        tester = PerturbationTester(
            strategy_runner=execute_user_strategy,
            backtest_engine_class=BacktestEngine,
            objective_fn=lambda m: m.get("sharpe_ratio", 0),
        )
        result = tester.run(
            df=df,
            strategy_code=code,
            best_params={"fast_period": 20, "slow_period": 50},
            base_params={},
        )
    """

    def __init__(
        self,
        strategy_runner: Callable,
        backtest_engine_class: type,
        objective_fn: Optional[Callable[[Dict], float]] = None,
        objective_name: str = "sharpe_ratio",
        direction: str = "maximize",
        direction_code: str = "long",
        perturbation_pcts: Optional[List[float]] = None,
        n_samples_per_param: int = 5,
        seed: int = 42,
    ):
        self.strategy_runner = strategy_runner
        self.backtest_engine_class = backtest_engine_class
        self.objective_name = objective_name
        self.objective_fn = objective_fn
        self.direction = direction
        self.direction_code = direction_code
        self.perturbation_pcts = perturbation_pcts or [-0.3, -0.15, -0.05, 0.05, 0.15, 0.3]
        self.n_samples_per_param = n_samples_per_param
        self.seed = seed

    def _perturb_value(self, value: Any, pct: float) -> Any:
        """對單個值做擾動"""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float, np.integer, np.floating)):
            v = float(value)
            new_v = v * (1 + pct)
            # 保持原來型別
            if isinstance(value, (int, np.integer)) and v == int(v):
                return max(1, int(round(new_v)))
            return new_v
        # 字串/categorical：不擾動
        return value

    def _build_perturbed_params(
        self,
        best_params: Dict[str, Any],
        param_name: str,
        pcts: List[float],
    ) -> List[Dict[str, Any]]:
        """產生擾動後的參數組"""
        results = []
        for pct in pcts:
            new_params = best_params.copy()
            if param_name in best_params:
                new_params[param_name] = self._perturb_value(best_params[param_name], pct)
            results.append(new_params)
        return results

    def _run_single(
        self,
        df: pd.DataFrame,
        strategy_code: str,
        params: Dict[str, Any],
        base_params: Dict[str, Any],
        initial_capital: float,
        commission: float,
        slippage: float,
    ) -> Optional[Dict[str, Any]]:
        """跑單次回測，回傳 metrics"""
        full_params = {**base_params, **params}
        try:
            result = self.strategy_runner(strategy_code, df, full_params)
        except Exception:
            return None

        if not isinstance(result, tuple) or len(result) not in (3, 7):
            return None
        if len(result) == 7:
            entries, exits, err, le, lx, se, sx = result
        else:
            entries, exits, err = result
        if err or not entries.any():
            return None

        try:
            engine = self.backtest_engine_class(
                df, initial_capital=initial_capital,
                commission=commission, slippage=slippage,
            )
            bt = engine.run(entries, exits, direction=self.direction_code)
        except Exception:
            return None

        metrics = bt.get("metrics", {})
        if "error" in metrics:
            return None
        return metrics

    def run(
        self,
        df: pd.DataFrame,
        strategy_code: str,
        best_params: Dict[str, Any],
        base_params: Optional[Dict[str, Any]] = None,
        initial_capital: float = 10000.0,
        commission: float = 0.001,
        slippage: float = 0.0005,
    ) -> Dict[str, Any]:
        """
        執行擾動測試

        Args:
            df: K 線
            strategy_code: 策略代碼
            best_params: 最佳參數
            base_params: 固定參數
            initial_capital, commission, slippage: 回測設定

        Returns:
            dict with keys:
                - baseline_value: 最佳參數的目標值
                - per_param: 每個參數的擾動結果 DataFrame
                - overall_cv: 所有擾動的變異係數
                - stability_score: 0-100 分（越高越穩定）
                - interpretation: 解釋文字
        """
        if base_params is None:
            base_params = {}

        # 1) 先跑 baseline
        baseline_metrics = self._run_single(
            df, strategy_code, best_params, base_params,
            initial_capital, commission, slippage,
        )
        if baseline_metrics is None:
            return {"error": "Baseline 跑失敗，無法做擾動測試"}

        if self.objective_fn:
            baseline_value = self.objective_fn(baseline_metrics)
        else:
            baseline_value = baseline_metrics.get(self.objective_name, 0)

        # 2) 對每個參數做擾動
        all_records = []

        for param_name in best_params.keys():
            # 產生擾動組
            perturbed_list = self._build_perturbed_params(
                best_params, param_name, self.perturbation_pcts,
            )

            for pct, params in zip(self.perturbation_pcts, perturbed_list):
                metrics = self._run_single(
                    df, strategy_code, params, base_params,
                    initial_capital, commission, slippage,
                )
                if metrics is None:
                    all_records.append({
                        "param_name": param_name,
                        "perturbation_pct": pct,
                        "new_value": params.get(param_name),
                        "value": np.nan,
                        "n_trades": 0,
                        "failed": True,
                    })
                    continue

                if self.objective_fn:
                    value = self.objective_fn(metrics)
                else:
                    value = metrics.get(self.objective_name, 0)

                all_records.append({
                    "param_name": param_name,
                    "perturbation_pct": pct,
                    "new_value": params.get(param_name),
                    "value": value,
                    "n_trades": metrics.get("n_trades", 0),
                    "sharpe": metrics.get("sharpe_ratio", 0),
                    "total_return_pct": metrics.get("total_return_pct", 0),
                    "max_drawdown_pct": metrics.get("max_drawdown_pct", 0),
                    "win_rate": metrics.get("win_rate", 0),
                    "failed": False,
                })

        df_pert = pd.DataFrame(all_records)

        # 3) 計算整體變異
        valid_values = df_pert["value"].dropna()
        if len(valid_values) >= 2:
            std_val = valid_values.std()
            mean_val = valid_values.mean()
            cv = std_val / abs(mean_val) if mean_val != 0 else 0
        else:
            cv = 0
            mean_val = baseline_value
            std_val = 0

        # 4) 每個參數的 CV
        per_param_cv = {}
        for param_name in best_params.keys():
            sub = df_pert[
                (df_pert["param_name"] == param_name) & (~df_pert["failed"])
            ]["value"]
            if len(sub) >= 2 and sub.mean() != 0:
                per_param_cv[param_name] = float(sub.std() / abs(sub.mean()))
            else:
                per_param_cv[param_name] = 0.0

        # 5) 穩定性評分（0-100）
        # CV 越低 → 越穩定 → 評分越高
        # CV=0 → 100, CV>=1 → 0
        stability_score = max(0, min(100, 100 * (1 - cv)))

        # 6) 解釋
        if stability_score >= 80:
            interpretation = "🟢 非常穩定：最佳參數附近表現一致，過擬合風險低"
        elif stability_score >= 60:
            interpretation = "🟡 尚可：最佳參數附近表現接近，整體穩健"
        elif stability_score >= 40:
            interpretation = "🟠 不太穩定：最佳參數附近波動較大，建議縮小搜尋範圍"
        else:
            interpretation = " 極不穩定：可能存在過擬合，不建議實盤使用"

        return {
            "baseline_value": baseline_value,
            "baseline_metrics": baseline_metrics,
            "per_param": df_pert,
            "per_param_cv": per_param_cv,
            "mean_perturbed_value": mean_val,
            "std_perturbed_value": std_val,
            "overall_cv": cv,
            "stability_score": stability_score,
            "interpretation": interpretation,
        }


__all__ = ["PerturbationTester"]
