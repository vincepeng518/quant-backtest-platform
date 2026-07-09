"""
自動參數優化模組
支援網格搜尋與隨機搜尋，並避免過擬合
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Tuple
from itertools import product
import random


class ParameterOptimizer:
    """
    參數優化器

    特色：
    1. 網格搜尋 / 隨機搜尋
    2. 多目標評分（Sharpe + 報酬 + 回撤）
    3. 過擬合偵測（參數平原度分析）
    4. 穩定度評分
    """

    def __init__(
        self,
        strategy_runner,
        backtest_engine_class,
        metric: str = "sharpe_ratio",
        min_trades: int = 5,
        n_jobs: int = 1,
    ):
        self.strategy_runner = strategy_runner
        self.backtest_engine_class = backtest_engine_class
        self.metric = metric
        self.min_trades = min_trades
        self.n_jobs = n_jobs

    def grid_search(
        self,
        df: pd.DataFrame,
        strategy_code: str,
        param_space: Dict[str, List],
        base_params: Dict[str, Any] = None,
        initial_capital: float = 10000,
        commission: float = 0.001,
        slippage: float = 0.0005,
        direction: str = "long",
        top_n: int = 20,
    ) -> Dict:
        """網格搜尋所有參數組合"""
        if base_params is None:
            base_params = {}

        param_names = list(param_space.keys())
        param_values_lists = [param_space[p] for p in param_names]

        # 計算總組合數
        total = 1
        for v in param_values_lists:
            total *= len(v)

        results = []
        for i, combo in enumerate(product(*param_values_lists)):
            params = {**base_params, **dict(zip(param_names, combo))}

            entries, exits, err = self.strategy_runner(strategy_code, df, params)
            if err or not entries.any():
                results.append({
                    "params": params,
                    "error": err or "無交易",
                })
                continue

            if entries.sum() < self.min_trades:
                results.append({
                    "params": params,
                    "error": f"交易數過少 ({entries.sum()})",
                })
                continue

            engine = self.backtest_engine_class(
                df, initial_capital=initial_capital,
                commission=commission, slippage=slippage,
            )
            try:
                bt_results = engine.run(entries, exits, direction=direction)
                metrics = bt_results["metrics"]
            except Exception as e:
                results.append({"params": params, "error": str(e)})
                continue

            if "error" in metrics:
                results.append({"params": params, "error": metrics["error"]})
                continue

            result = {
                "params": params,
                "error": None,
                **{k: v for k, v in metrics.items() if not isinstance(v, np.ndarray)},
            }
            results.append(result)

        # 過濾有效結果並排序
        valid = [r for r in results if r.get("error") is None]
        valid.sort(key=lambda x: x.get(self.metric, -np.inf), reverse=True)

        return {
            "all_results": results,
            "valid_results": valid,
            "top_results": valid[:top_n],
            "best_params": valid[0]["params"] if valid else None,
            "best_metrics": valid[0] if valid else None,
            "total_combinations": total,
            "valid_combinations": len(valid),
            "metric_used": self.metric,
        }

    def random_search(
        self,
        df: pd.DataFrame,
        strategy_code: str,
        param_space: Dict[str, List],
        base_params: Dict[str, Any] = None,
        initial_capital: float = 10000,
        commission: float = 0.001,
        slippage: float = 0.0005,
        direction: str = "long",
        n_iter: int = 100,
        top_n: int = 20,
    ) -> Dict:
        """
        隨機搜尋：適合參數空間很大時
        比網格搜尋快，且在實證上往往能找到同等或更好的解
        """
        if base_params is None:
            base_params = {}

        param_names = list(param_space.keys())
        param_values_lists = [param_space[p] for p in param_names]

        results = []
        for i in range(n_iter):
            combo = [random.choice(v) for v in param_values_lists]
            params = {**base_params, **dict(zip(param_names, combo))}

            entries, exits, err = self.strategy_runner(strategy_code, df, params)
            if err or not entries.any():
                continue

            if entries.sum() < self.min_trades:
                continue

            engine = self.backtest_engine_class(
                df, initial_capital=initial_capital,
                commission=commission, slippage=slippage,
            )
            try:
                bt_results = engine.run(entries, exits, direction=direction)
                metrics = bt_results["metrics"]
            except Exception:
                continue

            if "error" in metrics:
                continue

            result = {
                "params": params,
                "error": None,
                **{k: v for k, v in metrics.items() if not isinstance(v, np.ndarray)},
            }
            results.append(result)

        results.sort(key=lambda x: x.get(self.metric, -np.inf), reverse=True)

        return {
            "all_results": results,
            "valid_results": results,
            "top_results": results[:top_n],
            "best_params": results[0]["params"] if results else None,
            "best_metrics": results[0] if results else None,
            "total_combinations": n_iter,
            "valid_combinations": len(results),
            "metric_used": self.metric,
        }

    def analyze_param_sensitivity(
        self,
        df: pd.DataFrame,
        strategy_code: str,
        param_space: Dict[str, List],
        base_params: Dict[str, Any] = None,
        initial_capital: float = 10000,
        commission: float = 0.001,
        slippage: float = 0.0005,
        direction: str = "long",
    ) -> pd.DataFrame:
        """
        參數敏感度分析：
        - 每次只改一個參數，其他固定為最佳值
        - 計算該參數變化對指標的影響
        - 識別「參數平原」（param plateau）= 對結果影響小的區域
        """
        # 先做一次完整網格搜尋找最佳參數
        full_result = self.grid_search(
            df, strategy_code, param_space, base_params,
            initial_capital, commission, slippage, direction,
        )

        if not full_result["best_params"]:
            return pd.DataFrame()

        best_params = {p: full_result["best_params"][p] for p in param_space.keys()}

        sensitivity_data = []
        for pname, pvalues in param_space.items():
            for v in pvalues:
                test_params = best_params.copy()
                test_params[pname] = v
                test_params = {**base_params, **test_params}

                entries, exits, err = self.strategy_runner(strategy_code, df, test_params)
                if err or not entries.any():
                    continue

                engine = self.backtest_engine_class(
                    df, initial_capital=initial_capital,
                    commission=commission, slippage=slippage,
                )
                try:
                    bt_results = engine.run(entries, exits, direction=direction)
                    metrics = bt_results["metrics"]
                except Exception:
                    continue

                if "error" in metrics:
                    continue

                sensitivity_data.append({
                    "param_name": pname,
                    "param_value": v,
                    **{k: metrics[k] for k in ["sharpe_ratio", "total_return_pct", "max_drawdown_pct", "win_rate", "n_trades"] if k in metrics},
                })

        return pd.DataFrame(sensitivity_data)


def calculate_overfit_score(results: List[Dict], top_n: int = 10) -> Dict:
    """
    過擬合評分
    概念：比較前 N 名的指標差異
    - 如果前幾名指標都很接近 → 參數平原寬廣 → 較不易過擬合
    - 如果第一名遠好於第二名 → 尖峰最佳化 → 高度過擬合風險

    評分 0-100：
    - 100: 參數平原寬廣（健康）
    - 0: 尖峰最佳化（危險）
    """
    if len(results) < 2:
        return {"score": 0, "warning": "結果太少無法評估"}

    top = results[:top_n]
    metrics_list = [r.get("sharpe_ratio", 0) for r in top]
    best = metrics_list[0]

    if best <= 0:
        return {"score": 0, "warning": "最佳參數表現為負"}

    # 計算相對差異
    ratios = [m / best for m in metrics_list if best != 0]
    avg_ratio = np.mean(ratios) if ratios else 0

    # 標準化到 0-100
    # avg_ratio 越接近 1 表示前幾名指標越接近（平原寬廣）
    score = min(100, avg_ratio * 100)

    if score >= 80:
        warning = "🟢 參數平原寬廣：找到的解穩健，過擬合風險低"
    elif score >= 60:
        warning = "🟡 參數平原中等：有一定穩健性，但建議多做 walk-forward 驗證"
    elif score >= 40:
        warning = "🟠 參數平原狹窄：過擬合風險中等，建議保守倉位"
    else:
        warning = "🔴 尖峰最佳化：高度過擬合風險，不建議實盤使用"

    return {
        "score": score,
        "warning": warning,
        "avg_ratio": avg_ratio,
        "top_n_metrics": metrics_list,
    }
