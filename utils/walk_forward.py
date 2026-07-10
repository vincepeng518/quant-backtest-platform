"""
Walk-Forward 驗證模組
用於檢驗策略是否過擬合，方法是：
1. 將歷史資料切成多個時間段
2. 在 in-sample（訓練）段上最佳化參數
3. 在 out-of-sample（測試）段上驗證
4. 拼接所有 OOS 結果，計算綜合表現

支援兩種模式：
- 單標的：使用 BacktestEngine
- 配對交易：使用 PairBacktestEngine（傳入 pair_kwargs）

支援 3 種內部優化器：
- grid: 網格搜尋（向後相容）
- random: 隨機搜尋
- optuna: Optuna Bayesian Optimization（推薦）
- timeseries: 純 TimeSeriesSplit 交叉驗證（無 walk-forward）

"""
from __future__ import annotations

import time
import logging
from typing import Dict, List, Any, Tuple, Optional, Callable
from itertools import product
import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

logger = logging.getLogger(__name__)


class WalkForwardValidator:
    """
    Walk-Forward 驗證器

    範例：
    - 總資料 1000 根 K 線
    - 每個 window 400 根（in-sample 300 + out-of-sample 100）
    - 滾動步進 100 根
    - 會產生 7 個測試窗口
    """

    def __init__(
        self,
        strategy_runner: Callable,
        backtest_engine_class: type,
        n_splits: int = 5,
        train_ratio: float = 0.7,
        anchored: bool = False,
        inner_optimizer: str = "grid",  # "grid" / "random" / "optuna"
        inner_n_trials: int = 30,
        inner_objective: str = "sharpe_ratio",
        inner_seed: int = 42,
    ):
        """
        strategy_runner: 策略執行函數 execute_user_strategy
        backtest_engine_class: BacktestEngine 或 PairBacktestEngine 類別
        n_splits: 切分數量
        train_ratio: 每個 window 中訓練集佔比 (0.7 = 70% 訓練, 30% 測試)
        anchored: True=擴展窗口（從頭開始），False=滾動窗口
        inner_optimizer: 內部優化器（grid/random/optuna）
        inner_n_trials: 內部 trial 數（optuna/random 用）
        inner_objective: 目標函數
        inner_seed: 隨機種子
        """
        self.strategy_runner = strategy_runner
        self.backtest_engine_class = backtest_engine_class
        self.n_splits = n_splits
        self.train_ratio = train_ratio
        self.anchored = anchored
        self.inner_optimizer = inner_optimizer
        self.inner_n_trials = inner_n_trials
        self.inner_objective = inner_objective
        self.inner_seed = inner_seed

    def run(
        self,
        df: pd.DataFrame,
        strategy_code: str,
        param_space: Optional[Dict[str, List]] = None,
        param_specs: Optional[List[Dict[str, Any]]] = None,
        base_params: Optional[Dict[str, Any]] = None,
        fixed_params: Optional[Dict[str, Any]] = None,
        optimize_metric: Optional[str] = None,
        initial_capital: float = 10000.0,
        commission: float = 0.001,
        slippage: float = 0.0005,
        direction: str = "long",
        is_pair: bool = False,
        pair_kwargs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        執行 walk-forward 驗證

        Args:
            param_space: 網格搜尋用的 param_space（向後相容）
            param_specs: Optuna 用的 param_specs
            base_params: 固定參數
            fixed_params: 別名（向後相容）
            optimize_metric: 目標函數（grid/random 用）
        """
        if base_params is None:
            base_params = {}
        if fixed_params is not None:
            base_params = {**base_params, **fixed_params}
        if pair_kwargs is None:
            pair_kwargs = {}
        if optimize_metric is None:
            optimize_metric = self.inner_objective

        n = len(df)
        # 計算每個 window 的大小
        test_size = int(n * (1 - self.train_ratio) / self.n_splits)
        train_size = int(test_size * self.train_ratio / (1 - self.train_ratio))

        # 確保最小資料量
        if train_size < 50 or test_size < 20:
            return {"error": f"資料量不足以支援 {self.n_splits} 切分（需要至少 {self.n_splits * 70} 根 K 線）"}

        windows = []
        for i in range(self.n_splits):
            if self.anchored:
                train_start = 0
                train_end = train_size + i * test_size
            else:
                train_start = i * test_size
                train_end = train_start + train_size

            test_start = train_end
            test_end = test_start + test_size

            if test_end > n:
                break

            windows.append({
                "split_id": i + 1,
                "train_start": train_start,
                "train_end": train_end,
                "test_start": test_start,
                "test_end": test_end,
            })

        # 配對模式的 direction 轉換
        pair_direction = None
        if is_pair:
            pair_direction = "pair_long" if direction == "long" else "pair_short"

        # 執行每個 window
        all_results = []
        for win in windows:
            train_df = df.iloc[win["train_start"]:win["train_end"]].copy()
            test_df = df.iloc[win["test_start"]:win["test_end"]].copy()

            # 在訓練集上做內部優化
            if self.inner_optimizer == "optuna" and param_specs:
                best_params, train_metric = self._optuna_search(
                    train_df, strategy_code, param_specs, base_params,
                    optimize_metric, initial_capital, commission, slippage,
                    direction, is_pair, pair_kwargs,
                )
            else:
                # 用 grid/random（向後相容）
                best_params, train_metric = self._grid_search(
                    train_df, strategy_code,
                    param_space or _specs_to_grid_space(param_specs or []),
                    base_params, optimize_metric, initial_capital, commission,
                    slippage, direction, is_pair, pair_kwargs,
                )

            # 用最佳參數在測試集上跑
            full_params = {**base_params, **best_params}
            # 解構 7 個元素（向後兼容 3 個）
            _wf_result = self.strategy_runner(strategy_code, test_df, full_params)
            if not isinstance(_wf_result, tuple) or len(_wf_result) not in (3, 7):
                all_results.append({
                    **win,
                    "best_params": best_params,
                    "train_metric": train_metric,
                    "test_metric": None,
                    "error": f"策略回傳格式錯誤",
                })
                continue
            if len(_wf_result) == 7:
                test_entries, test_exits, err, _le, _lx, _se, _sx = _wf_result
            else:
                test_entries, test_exits, err = _wf_result

            if err or not test_entries.any():
                # 沒有交易，記錄空結果
                all_results.append({
                    **win,
                    "best_params": best_params,
                    "train_metric": train_metric,
                    "test_metric": None,
                    "error": err or "無交易",
                })
                continue

            # 跑回測
            if is_pair:
                engine = self.backtest_engine_class(
                    test_df,
                    initial_capital=initial_capital,
                    commission=commission,
                    slippage=slippage,
                    **pair_kwargs,
                )
                test_results = engine.run(test_entries, test_exits, direction=pair_direction)
            else:
                engine = self.backtest_engine_class(
                    test_df,
                    initial_capital=initial_capital,
                    commission=commission,
                    slippage=slippage,
                )
                test_results = engine.run(test_entries, test_exits, direction=direction)

            test_metrics = test_results["metrics"]

            all_results.append({
                **win,
                "best_params": best_params,
                "train_metric": train_metric,
                "test_metric": test_metrics.get(optimize_metric, None) if "error" not in test_metrics else None,
                "test_return": test_metrics.get("total_return_pct", 0),
                "test_drawdown": test_metrics.get("max_drawdown_pct", 0),
                "test_n_trades": test_metrics.get("n_trades", 0),
                "test_win_rate": test_metrics.get("win_rate", 0),
                "test_sharpe": test_metrics.get("sharpe_ratio", 0),
            })

        # 計算綜合 OOS 指標
        combined_oos = self._combine_oos_equity(
            df, all_results, strategy_code, base_params,
            initial_capital, commission, slippage, direction,
            is_pair, pair_kwargs,
        )

        # 計算過擬合程度
        valid = [r for r in all_results if r.get("test_metric") is not None]
        if valid:
            avg_train = np.mean([r["train_metric"] for r in valid])
            avg_test = np.mean([r["test_metric"] for r in valid])
            degradation = (avg_train - avg_test) / abs(avg_train) * 100 if avg_train != 0 else 0
        else:
            avg_train = avg_test = degradation = 0

        return {
            "windows": all_results,
            "n_windows": len(all_results),
            "combined_oos_metrics": combined_oos,
            "avg_train_metric": avg_train,
            "avg_test_metric": avg_test,
            "degradation_pct": degradation,
            "parameter_stability": self._calc_param_stability(all_results),
            "is_pair": is_pair,
            "inner_optimizer": self.inner_optimizer,
        }

    def _optuna_search(
        self, df, strategy_code, param_specs, base_params, metric,
        capital, commission, slippage, direction, is_pair, pair_kwargs,
    ) -> Tuple[Dict, float]:
        """用 Optuna 在訓練集上找最佳參數"""
        from .optuna_optimizer import OptunaOptimizer

        opt = OptunaOptimizer(
            strategy_runner=self.strategy_runner,
            backtest_engine_class=self.backtest_engine_class,
            objective_name=metric,
            sampler="tpe",
            pruner="none",  # WF 內部用 nop pruner（不剪枝）
            seed=self.inner_seed,
            min_trades=2,  # WF 內部降低 min_trades（資料較少）
        )

        try:
            result = opt.run(
                df=df,
                strategy_code=strategy_code,
                param_specs=param_specs,
                base_params=base_params,
                initial_capital=capital,
                commission=commission,
                slippage=slippage,
                direction=direction,
                n_trials=self.inner_n_trials,
                study_name=f"wf_inner_{int(time.time()*1000)}",
                persist=False,
            )
        except Exception as e:
            logger.warning(f"WF inner optuna failed: {e}")
            return {}, 0.0

        best_params = result.get("best_params") or {}
        best_value = result.get("best_value", 0) or 0
        return best_params, float(best_value)

    def _grid_search(
        self, df, strategy_code, param_space, base_params, metric,
        capital, commission, slippage, direction, is_pair, pair_kwargs,
    ) -> Tuple[Dict, float]:
        """網格搜尋最佳參數"""
        param_names = list(param_space.keys())
        param_values = [param_space[p] for p in param_names]

        best_params = {}
        best_metric = -np.inf

        for combo in product(*param_values):
            params = {**base_params, **dict(zip(param_names, combo))}

            # 解構 7 個元素（向後兼容 3 個）
            _wf_result = self.strategy_runner(strategy_code, df, params)
            if not isinstance(_wf_result, tuple) or len(_wf_result) not in (3, 7):
                continue
            if len(_wf_result) == 7:
                entries, exits, err, _le, _lx, _se, _sx = _wf_result
            else:
                entries, exits, err = _wf_result
            if err or not entries.any() or entries.sum() < 3:
                continue

            # 跑回測
            if is_pair:
                engine = self.backtest_engine_class(
                    df, initial_capital=capital, commission=commission,
                    slippage=slippage, **pair_kwargs,
                )
                pair_dir = "pair_long" if direction == "long" else "pair_short"
                results = engine.run(entries, exits, direction=pair_dir)
            else:
                engine = self.backtest_engine_class(
                    df, initial_capital=capital, commission=commission, slippage=slippage,
                )
                results = engine.run(entries, exits, direction=direction)

            metrics = results["metrics"]

            if "error" in metrics:
                continue

            value = metrics.get(metric, -np.inf)
            # 加上最少交易數懲罰
            if metrics.get("n_trades", 0) < 5:
                value -= 1

            if value > best_metric:
                best_metric = value
                best_params = dict(zip(param_names, combo))

        return best_params, best_metric

    def _combine_oos_equity(
        self, df, windows_results, strategy_code, base_params,
        capital, commission, slippage, direction, is_pair, pair_kwargs,
    ) -> Dict:
        """拼接所有 OOS 段的權益曲線"""
        all_oos_trades = []
        for win in windows_results:
            if "best_params" not in win or not win.get("best_params"):
                continue

            test_df = df.iloc[win["test_start"]:win["test_end"]].copy()
            full_params = {**base_params, **win["best_params"]}

            # 解構 7 個元素（向後兼容 3 個）
            _wf_result = self.strategy_runner(strategy_code, test_df, full_params)
            if not isinstance(_wf_result, tuple) or len(_wf_result) not in (3, 7):
                continue
            if len(_wf_result) == 7:
                entries, exits, err, _le, _lx, _se, _sx = _wf_result
            else:
                entries, exits, err = _wf_result
            if err or not entries.any():
                continue

            if is_pair:
                engine = self.backtest_engine_class(
                    test_df, initial_capital=capital, commission=commission,
                    slippage=slippage, **pair_kwargs,
                )
                pair_dir = "pair_long" if direction == "long" else "pair_short"
                results = engine.run(entries, exits, direction=pair_dir)
            else:
                engine = self.backtest_engine_class(
                    test_df, initial_capital=capital, commission=commission, slippage=slippage,
                )
                results = engine.run(entries, exits, direction=direction)

            all_oos_trades.extend(results["trades"])

        if not all_oos_trades:
            return {"error": "無 OOS 交易"}

        # 簡化：直接計算統計
        trades_df = pd.DataFrame(all_oos_trades)
        total_return = (1 + trades_df["pnl_pct"]).prod() - 1
        n_trades = len(trades_df)
        win_rate = (trades_df["pnl_pct"] > 0).sum() / n_trades * 100
        avg_pnl = trades_df["pnl_pct"].mean() * 100
        max_loss = trades_df["pnl_pct"].min() * 100

        result = {
            "n_oos_trades": n_trades,
            "oos_total_return_pct": total_return * 100,
            "oos_win_rate": win_rate,
            "oos_avg_pnl_pct": avg_pnl,
            "oos_max_single_loss_pct": max_loss,
        }

        # 配對模式：加上兩邊各自的損益統計
        if is_pair and "pnl1_pct" in trades_df.columns:
            result["oos_pnl1_pct"] = trades_df["pnl1_pct"].mean() * 100
            result["oos_pnl2_pct"] = trades_df["pnl2_pct"].mean() * 100

        return result

    def _calc_param_stability(self, windows_results) -> Dict:
        """計算參數穩定度（不同 window 選出的參數有多接近）"""
        valid = [w for w in windows_results if w.get("best_params")]
        if len(valid) < 2:
            return {"score": 0, "note": "資料不足"}

        param_names = list(valid[0]["best_params"].keys())
        stabilities = {}

        for pname in param_names:
            values = [w["best_params"][pname] for w in valid]
            if all(isinstance(v, (int, float, np.integer, np.floating)) for v in values):
                mean = np.mean(values)
                std = np.std(values)
                cv = (std / abs(mean)) if mean != 0 else 0
                stabilities[pname] = {
                    "mean": mean,
                    "std": std,
                    "cv": cv,
                    "values": values,
                }

        # 整體穩定度分數：CV 越低越好（0 = 完美穩定）
        avg_cv = np.mean([s["cv"] for s in stabilities.values()]) if stabilities else 0
        score = max(0, 100 - avg_cv * 100)  # 簡單轉換為 0-100 分

        return {
            "score": score,
            "avg_cv": avg_cv,
            "details": stabilities,
            "interpretation": self._interpret_stability(score),
        }

    def _interpret_stability(self, score: float) -> str:
        if score >= 80:
            return "🟢 非常穩定：參數在不同區段表現一致，泛化能力強"
        elif score >= 60:
            return "🟡 尚可：參數有些波動，但整體趨勢一致"
        elif score >= 40:
            return "🟠 不穩定：參數在不同區段差異大，可能有過擬合"
        else:
            return "🔴 極不穩定：強烈建議重新設計策略或縮小參數空間"


# === TimeSeriesSplit 交叉驗證 ===

def timeseries_split_validate(
    df: pd.DataFrame,
    strategy_code: str,
    param_specs: List[Dict[str, Any]],
    strategy_runner: Callable,
    backtest_engine_class: type,
    n_splits: int = 5,
    base_params: Optional[Dict[str, Any]] = None,
    objective_name: str = "sharpe_ratio",
    initial_capital: float = 10000.0,
    commission: float = 0.001,
    slippage: float = 0.0005,
    direction: str = "long",
    n_trials_per_fold: int = 30,
    seed: int = 42,
) -> Dict[str, Any]:
    """
    TimeSeriesSplit 交叉驗證（純 CV，無 walk-forward 結構）

    流程：
    1. 用 TimeSeriesSplit 把資料切成 K 個 fold（時序保持）
    2. 每個 fold：前 (k-1) 做訓練，最後一個做測試
    3. 在每個 fold 的訓練段用 Optuna 找最佳參數
    4. 在測試段驗證
    5. 聚合所有 fold 的測試結果

    Returns:
        dict with:
            - fold_results: 每個 fold 的結果
            - mean_test_metric, std_test_metric
            - mean_params: 跨 fold 參數平均
    """
    if base_params is None:
        base_params = {}

    tss = TimeSeriesSplit(n_splits=n_splits)
    fold_results = []
    all_test_params = []
    test_values = []

    for fold_id, (train_idx, test_idx) in enumerate(tss.split(df)):
        train_df = df.iloc[train_idx].copy()
        test_df = df.iloc[test_idx].copy()

        # 訓練：Optuna 找最佳
        from .optuna_optimizer import OptunaOptimizer

        opt = OptunaOptimizer(
            strategy_runner=strategy_runner,
            backtest_engine_class=backtest_engine_class,
            objective_name=objective_name,
            sampler="tpe",
            pruner="median",
            seed=seed + fold_id,
        )
        train_result = opt.run(
            df=train_df,
            strategy_code=strategy_code,
            param_specs=param_specs,
            base_params=base_params,
            initial_capital=initial_capital,
            commission=commission,
            slippage=slippage,
            direction=direction,
            n_trials=n_trials_per_fold,
            study_name=f"tscv_fold_{fold_id}_{int(time.time()*1000)}",
            persist=False,
        )

        # 測試
        best_params = train_result["best_params"]
        full_params = {**base_params, **best_params}
        _result = strategy_runner(strategy_code, test_df, full_params)
        if not isinstance(_result, tuple) or len(_result) not in (3, 7):
            fold_results.append({
                "fold": fold_id + 1,
                "best_params": best_params,
                "train_value": train_result.get("best_value"),
                "test_value": None,
                "error": "策略回傳錯誤",
            })
            continue
        if len(_result) == 7:
            entries, exits, err, _le, _lx, _se, _sx = _result
        else:
            entries, exits, err = _result
        if err or not entries.any():
            fold_results.append({
                "fold": fold_id + 1,
                "best_params": best_params,
                "train_value": train_result.get("best_value"),
                "test_value": None,
                "error": err or "無交易",
            })
            continue

        try:
            engine = backtest_engine_class(
                test_df, initial_capital=initial_capital,
                commission=commission, slippage=slippage,
            )
            bt = engine.run(entries, exits, direction=direction)
            test_metrics = bt["metrics"]
        except Exception as e:
            fold_results.append({
                "fold": fold_id + 1,
                "best_params": best_params,
                "train_value": train_result.get("best_value"),
                "test_value": None,
                "error": str(e),
            })
            continue

        from .objective_builder import get_objective_fn
        test_value = get_objective_fn(objective_name)(test_metrics)

        fold_results.append({
            "fold": fold_id + 1,
            "best_params": best_params,
            "train_value": train_result.get("best_value"),
            "test_value": test_value,
            "test_metrics": test_metrics,
            "n_test_trades": test_metrics.get("n_trades", 0),
        })
        all_test_params.append(best_params)
        test_values.append(test_value)

    # 聚合
    valid = [r for r in fold_results if r.get("test_value") is not None]
    if valid:
        mean_test = np.mean([r["test_value"] for r in valid])
        std_test = np.std([r["test_value"] for r in valid])
    else:
        mean_test = std_test = 0

    # 跨 fold 平均參數（僅對數值型）
    mean_params = {}
    if all_test_params:
        keys = all_test_params[0].keys()
        for k in keys:
            vals = [p[k] for p in all_test_params if isinstance(p.get(k), (int, float))]
            if vals:
                mean_params[k] = float(np.mean(vals))

    return {
        "fold_results": fold_results,
        "n_folds": n_splits,
        "mean_test_value": mean_test,
        "std_test_value": std_test,
        "mean_params": mean_params,
    }


def _specs_to_grid_space(param_specs: List[Dict[str, Any]]) -> Dict[str, List]:
    """把 param_specs 轉成 grid search 的 param_space（向後相容）"""
    grid_space = {}
    for spec in param_specs:
        name = spec["name"]
        ptype = spec.get("type", "int")
        if ptype == "int":
            low, high = int(spec["low"]), int(spec["high"])
            step = int(spec.get("step", max(1, (high - low) // 10)))
            grid_space[name] = list(range(low, high + 1, step))
        elif ptype in ("float", "float_log", "loguniform"):
            low, high = float(spec["low"]), float(spec["high"])
            n = 10
            if ptype in ("float_log", "loguniform"):
                grid_space[name] = list(np.logspace(np.log10(low), np.log10(high), n))
            else:
                grid_space[name] = list(np.linspace(low, high, n))
        elif ptype == "categorical":
            grid_space[name] = list(spec["choices"])
    return grid_space


__all__ = [
    "WalkForwardValidator",
    "timeseries_split_validate",
    "_specs_to_grid_space",
]
