"""
Optuna 優化器 - Bayesian Optimization 核心

特色：
1. 預設使用 TPESampler（Bayesian Optimization）+ MedianPruner
2. 可切換 GridSampler（向後相容舊版）
3. 支援 4 種參數型態：int, float (log=True), float (linear), categorical
4. 自訂目標函數
5. Pruner 提前剪枝
6. 自動持久化（SQLite + Parquet）
7. 參數重要性分析
8. n_trials, timeout 支援
9. 隨機種子固定（可重現）
"""
from __future__ import annotations

import time
import json
import sqlite3
import logging
from typing import Dict, List, Any, Optional, Callable, Tuple
from pathlib import Path

import numpy as np
import pandas as pd
import optuna
from optuna.samplers import TPESampler, GridSampler, RandomSampler
from optuna.pruners import MedianPruner, NopPruner, BasePruner
from optuna.importance import get_param_importances, FanovaImportanceEvaluator

from .seed import set_global_seed, seed_for_trial
from .objective_builder import get_objective_fn, OBJECTIVE_REGISTRY
from .study_storage import (
    init_db,
    save_study_meta,
    save_trial_meta,
    save_trial_result,
    get_sqlite_url,
    list_trial_metadata,
    load_trial_result,
)

logger = logging.getLogger(__name__)


# === 參數空間定義 ===

# 支援的參數型態
PARAM_TYPES = ("int", "float", "float_log", "categorical")


def _build_search_space(
    trial: optuna.Trial,
    param_specs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    從 param_specs 建立 Optuna 搜尋空間

    param_specs 格式:
        [
            {"name": "fast_period", "type": "int", "low": 5, "high": 50},
            {"name": "risk_pct", "type": "float_log", "low": 0.005, "high": 0.03},
            {"name": "ma_type", "type": "categorical", "choices": ["sma", "ema"]},
            {"name": "threshold", "type": "float", "low": 0.1, "high": 1.0, "log": False},
        ]
    """
    params = {}
    for spec in param_specs:
        name = spec["name"]
        ptype = spec.get("type", "int")

        if ptype == "int":
            params[name] = trial.suggest_int(
                name,
                int(spec["low"]),
                int(spec["high"]),
                step=int(spec.get("step", 1)),
            )
        elif ptype == "float" or ptype == "float_log":
            log = (ptype == "float_log") or bool(spec.get("log", False))
            params[name] = trial.suggest_float(
                name,
                float(spec["low"]),
                float(spec["high"]),
                log=log,
            )
        elif ptype == "categorical":
            params[name] = trial.suggest_categorical(name, list(spec["choices"]))
        elif ptype == "loguniform":
            # 對數尺度均勻分佈
            params[name] = trial.suggest_float(
                name,
                float(spec["low"]),
                float(spec["high"]),
                log=True,
            )
        else:
            raise ValueError(f"不支援的參數型態: {ptype}")
    return params


# === 核心 Optimizer 類別 ===

class OptunaOptimizer:
    """
    Optuna 優化器

    範例:
        opt = OptunaOptimizer(
            strategy_runner=execute_user_strategy,
            backtest_engine_class=BacktestEngine,
            objective_name="sharpe_ratio",
        )
        param_specs = [
            {"name": "fast_period", "type": "int", "low": 5, "high": 50},
            {"name": "slow_period", "type": "int", "low": 30, "high": 200},
        ]
        result = opt.run(
            df=df,
            strategy_code=strategy_code,
            param_specs=param_specs,
            fixed_params={"risk_pct": 0.01},
            n_trials=50,
        )
    """

    def __init__(
        self,
        strategy_runner: Callable,
        backtest_engine_class: type,
        objective_name: str = "sharpe_ratio",
        sampler: str = "tpe",  # "tpe" / "random" / "grid"
        pruner: str = "median",  # "median" / "none"
        direction: str = "maximize",
        min_trades: int = 5,
        seed: int = 42,
        n_jobs: int = 1,
        is_pair: bool = False,
    ):
        """
        Args:
            strategy_runner: 策略執行函數 execute_user_strategy
            backtest_engine_class: BacktestEngine 類別
            objective_name: 目標函數名稱（見 objective_builder.OBJECTIVE_REGISTRY）
            sampler: 採樣器（tpe/random/grid）
            pruner: 剪枝器（median/none）
            direction: 優化方向（maximize/minimize）
            min_trades: 最低交易數（少於此數的 trial 會被剪枝）
            seed: 隨機種子
            n_jobs: 並行數（Streamlit 預設 1）
            is_pair: 是否為配對交易
        """
        self.strategy_runner = strategy_runner
        self.backtest_engine_class = backtest_engine_class
        self.objective_name = objective_name
        self.objective_fn = get_objective_fn(objective_name)
        self.sampler_name = sampler
        self.pruner_name = pruner
        self.direction = direction
        self.min_trades = min_trades
        self.seed = seed
        self.n_jobs = n_jobs
        self.is_pair = is_pair

        # 設定全域種子
        set_global_seed(seed)

    def _build_sampler(self, study: optuna.Study, param_specs: List[Dict[str, Any]]):
        """建立 Optuna sampler"""
        if self.sampler_name == "tpe":
            return TPESampler(
                seed=self.seed,
                n_startup_trials=10,
                multivariate=True,  # 考慮參數相關性
            )
        elif self.sampler_name == "random":
            return RandomSampler(seed=self.seed)
        elif self.sampler_name == "grid":
            # GridSampler 需要完整網格
            search_space = {}
            for spec in param_specs:
                name = spec["name"]
                ptype = spec.get("type", "int")
                if ptype == "int":
                    low, high = int(spec["low"]), int(spec["high"])
                    step = int(spec.get("step", max(1, (high - low) // 10)))
                    search_space[name] = list(range(low, high + 1, step))
                elif ptype in ("float", "float_log", "loguniform"):
                    low, high = float(spec["low"]), float(spec["high"])
                    n = 10
                    if ptype in ("float_log", "loguniform"):
                        search_space[name] = list(np.logspace(np.log10(low), np.log10(high), n))
                    else:
                        search_space[name] = list(np.linspace(low, high, n))
                elif ptype == "categorical":
                    search_space[name] = list(spec["choices"])
            return GridSampler(search_space=search_space, seed=self.seed)
        else:
            raise ValueError(f"不支援的 sampler: {self.sampler_name}")

    def _build_pruner(self) -> BasePruner:
        """建立 pruner"""
        if self.pruner_name == "median":
            return MedianPruner(
                n_startup_trials=5,
                n_warmup_steps=3,
                interval_steps=1,
            )
        elif self.pruner_name == "none":
            return NopPruner()
        else:
            raise ValueError(f"不支援的 pruner: {self.pruner_name}")

    def _run_trial(
        self,
        df: pd.DataFrame,
        strategy_code: str,
        params: Dict[str, Any],
        base_params: Dict[str, Any],
        initial_capital: float,
        commission: float,
        slippage: float,
        direction: str,
    ) -> Tuple[Optional[Dict], Optional[pd.DataFrame], Optional[List[Dict]]]:
        """
        跑單個 trial（不涉及 Optuna API）

        Returns:
            (metrics, equity_curve_df, trades) 或 (None, None, None) 表示失敗
        """
        # 合併參數
        full_params = {**base_params, **params}

        # 為這個 trial 設定獨立種子
        # （已在外層設定，這裡不需再做）

        # 執行策略
        try:
            result = self.strategy_runner(strategy_code, df, full_params)
        except Exception as e:
            logger.warning(f"策略執行失敗: {e}")
            return None, None, None

        # 解構 7 個元素（向後兼容 3 個）
        if not isinstance(result, tuple) or len(result) not in (3, 7):
            return None, None, None

        if len(result) == 7:
            entries, exits, err, long_entries, long_exits, short_entries, short_exits = result
        else:
            entries, exits, err = result
            long_entries = long_exits = short_entries = short_exits = None

        if err or not entries.any():
            return None, None, None

        if entries.sum() < 1:
            return None, None, None

        # 跑回測
        try:
            engine = self.backtest_engine_class(
                df,
                initial_capital=initial_capital,
                commission=commission,
                slippage=slippage,
            )
            bt_results = engine.run(
                entries, exits,
                direction=direction,
                long_entries=long_entries,
                long_exits=long_exits,
                short_entries=short_entries,
                short_exits=short_exits,
            )
        except Exception as e:
            logger.warning(f"回測失敗: {e}")
            return None, None, None

        metrics = bt_results["metrics"]
        if "error" in metrics:
            return None, None, None

        return metrics, bt_results.get("data"), bt_results.get("trades")

    def run(
        self,
        df: pd.DataFrame,
        strategy_code: str,
        param_specs: List[Dict[str, Any]],
        base_params: Optional[Dict[str, Any]] = None,
        fixed_params: Optional[Dict[str, Any]] = None,
        initial_capital: float = 10000.0,
        commission: float = 0.001,
        slippage: float = 0.0005,
        direction: str = "long",
        n_trials: int = 50,
        timeout: Optional[float] = None,
        study_name: str = "optuna_study",
        persist: bool = True,
        progress_callback: Optional[Callable[[int, int, float, float, Dict], None]] = None,
    ) -> Dict[str, Any]:
        """
        執行 Optuna 優化

        Args:
            df: K 線資料
            strategy_code: 策略代碼
            param_specs: 參數空間定義（list of dicts）
            base_params: 固定參數（不被優化）
            fixed_params: 同 base_params（向後相容別名）
            initial_capital: 初始資金
            commission: 手續費
            slippage: 滑點
            direction: 交易方向
            n_trials: trial 數量
            timeout: 超時（秒）
            study_name: study 名稱
            persist: 是否持久化到 SQLite + Parquet
            progress_callback: 進度回呼 callback(trial_number, total_trials, current_value, best_value, current_params)

        Returns:
            dict with keys:
                - study: optuna.Study 物件
                - best_params: 最佳參數
                - best_value: 最佳目標值
                - best_metrics: 最佳 trial 的 metrics
                - all_trials: 所有 trial 的結果（DataFrame）
                - param_importances: 參數重要性 dict
                - n_trials_completed: 完成的 trial 數
        """
        # 合併 base_params / fixed_params（向後相容）
        if base_params is None:
            base_params = {}
        if fixed_params is not None:
            base_params = {**base_params, **fixed_params}

        if not param_specs:
            raise ValueError("param_specs 不能為空")

        # 初始化 DB
        if persist:
            init_db()

        # 建立 storage
        storage = None
        if persist:
            try:
                storage = optuna.storages.RDBStorage(url=get_sqlite_url(study_name))
            except Exception as e:
                logger.warning(f"建立 SQLite storage 失敗，改用 in-memory: {e}")
                storage = None

        # 建立 sampler 與 pruner
        sampler = self._build_sampler(None, param_specs)
        pruner = self._build_pruner()

        # 建立 study
        try:
            study = optuna.create_study(
                study_name=study_name,
                direction=self.direction,
                sampler=sampler,
                pruner=pruner,
                storage=storage,
                load_if_exists=True,
            )
        except Exception as e:
            logger.warning(f"建立 study 失敗（{e}），改用 in-memory")
            study = optuna.create_study(
                study_name=study_name,
                direction=self.direction,
                sampler=sampler,
                pruner=pruner,
            )

        # 記錄 study metadata
        if persist:
            save_study_meta(
                study_name=study_name,
                direction=self.direction,
                sampler=self.sampler_name,
                pruner=self.pruner_name,
                n_trials=0,  # 將在結尾更新
                best_value=None,
                best_params=None,
                extra_config={
                    "n_trials_requested": n_trials,
                    "timeout": timeout,
                    "objective_name": self.objective_name,
                    "param_specs": param_specs,
                    "base_params": base_params,
                    "seed": self.seed,
                },
            )

        # 統計
        start_time = time.time()
        best_value_so_far = -np.inf if self.direction == "maximize" else np.inf
        n_completed = 0
        n_pruned = 0
        n_failed = 0
        trial_records: List[Dict] = []

        # 客製化 trial 物件
        def objective(trial: optuna.Trial) -> float:
            nonlocal n_completed, n_pruned, n_failed, best_value_so_far

            # 1) 從 param_specs 採樣
            params = _build_search_space(trial, param_specs)

            # 2) 為 trial 設定獨立種子
            trial_seed = seed_for_trial(trial.number, self.seed)
            set_global_seed(trial_seed)

            # 3) 跑回測
            metrics, equity_curve, trades = self._run_trial(
                df, strategy_code, params, base_params,
                initial_capital, commission, slippage, direction,
            )

            if metrics is None:
                n_failed += 1
                raise optuna.TrialPruned(f"回測失敗或無交易")

            # 4) 檢查最少交易數
            n_trades = metrics.get("n_trades", 0)
            if n_trades < self.min_trades:
                n_pruned += 1
                raise optuna.TrialPruned(f"交易數過少 ({n_trades} < {self.min_trades})")

            # 5) 計算目標
            value = self.objective_fn(metrics)
            n_completed += 1

            # 6) 更新 best
            if self.direction == "maximize":
                if value > best_value_so_far:
                    best_value_so_far = value
            else:
                if value < best_value_so_far:
                    best_value_so_far = value

            # 7) 記錄到 user_attrs
            trial.set_user_attr("n_trades", n_trades)
            trial.set_user_attr("metrics", _jsonable(metrics))

            # 8) 持久化 parquet
            if persist:
                try:
                    save_trial_result(
                        study_name=study_name,
                        trial_number=trial.number,
                        metrics=metrics,
                        params=params,
                        trades=trades,
                        equity_curve=equity_curve,
                    )
                except Exception as e:
                    logger.warning(f"儲存 parquet 失敗: {e}")

                # 8.5) 寫 trial metadata 到自定義 SQLite（在 trial 完成後一次性 commit）
                try:
                    save_trial_meta(
                        study_name=study_name,
                        number=trial.number,
                        value=value,
                        state="complete",
                        params=params,
                        user_attrs={"n_trades": n_trades, "metrics": _jsonable(metrics)},
                    )
                except Exception as e:
                    logger.warning(f"儲存 trial metadata 失敗: {e}")

            # 9) 進度回呼
            if progress_callback:
                try:
                    progress_callback(
                        trial.number + 1,
                        n_trials,
                        value,
                        best_value_so_far,
                        params,
                    )
                except Exception:
                    pass

            # 記錄
            trial_records.append({
                "number": trial.number,
                "value": value,
                "params": params,
                "metrics": metrics,
                "state": "complete",
            })

            return value

        # 執行優化
        try:
            study.optimize(
                objective,
                n_trials=n_trials,
                timeout=timeout,
                n_jobs=1,  # Streamlit 環境避免並行 pickle 問題
                show_progress_bar=False,
            )
        except KeyboardInterrupt:
            logger.info("用戶中斷優化")

        # 計算結果
        elapsed = time.time() - start_time
        try:
            best_trial = study.best_trial
            best_params = best_trial.params if best_trial else {}
            best_value = float(best_trial.value) if best_trial and best_trial.value is not None else None
        except (ValueError, KeyError):
            best_trial = None
            best_params = {}
            best_value = None

        # 最佳 metrics
        best_metrics = {}
        if best_trial and best_trial.user_attrs.get("metrics"):
            best_metrics = best_trial.user_attrs["metrics"]

        # 參數重要性（fANOVA）
        param_importances = {}
        try:
            if len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]) >= 2:
                param_importances = get_param_importances(study)
                # 轉成 dict
                param_importances = {k: float(v) for k, v in param_importances.items()}
        except Exception as e:
            logger.warning(f"參數重要性計算失敗: {e}")

        # 構造 DataFrame
        trials_df = _trials_to_dataframe(study)

        # 更新 study metadata
        if persist:
            save_study_meta(
                study_name=study_name,
                direction=self.direction,
                sampler=self.sampler_name,
                pruner=self.pruner_name,
                n_trials=len(study.trials),
                best_value=best_value,
                best_params=best_params,
                extra_config={
                    "n_trials_requested": n_trials,
                    "timeout": timeout,
                    "objective_name": self.objective_name,
                    "param_specs": param_specs,
                    "base_params": base_params,
                    "seed": self.seed,
                    "elapsed_seconds": elapsed,
                    "n_pruned": n_pruned,
                    "n_failed": n_failed,
                },
            )

        return {
            "study": study,
            "best_params": best_params,
            "best_value": best_value,
            "best_metrics": best_metrics,
            "best_trial": best_trial,
            "all_trials": trials_df,
            "param_importances": param_importances,
            "n_trials_completed": n_completed,
            "n_trials_pruned": n_pruned,
            "n_trials_failed": n_failed,
            "n_trials_total": len(study.trials),
            "elapsed_seconds": elapsed,
            "study_name": study_name,
            "param_specs": param_specs,
            "objective_name": self.objective_name,
        }


def _jsonable(obj):
    """numpy/pandas 轉 JSON"""
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


def _trials_to_dataframe(study: optuna.Study) -> pd.DataFrame:
    """把 study 的 trials 轉成 DataFrame"""
    rows = []
    for t in study.trials:
        # 跳過 RUNNING / FAIL 的
        if t.state == optuna.trial.TrialState.RUNNING:
            continue
        row = {
            "number": t.number,
            "state": t.state.name,
            "value": t.value,
            "datetime_start": t.datetime_start.isoformat() if t.datetime_start else None,
            "datetime_complete": t.datetime_complete.isoformat() if t.datetime_complete else None,
            "duration_seconds": (t.datetime_complete - t.datetime_start).total_seconds() if t.datetime_start and t.datetime_complete else None,
        }
        # 攤平 params
        for k, v in (t.params or {}).items():
            row[f"param_{k}"] = v
        # 攤平 metrics
        for k, v in (t.user_attrs.get("metrics") or {}).items():
            if not isinstance(v, (list, dict)):
                row[f"metric_{k}"] = v
        row["n_trades"] = t.user_attrs.get("n_trades", 0)
        rows.append(row)
    return pd.DataFrame(rows)


__all__ = [
    "OptunaOptimizer",
    "PARAM_TYPES",
    "_build_search_space",
]
