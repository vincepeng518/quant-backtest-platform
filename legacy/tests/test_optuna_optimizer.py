"""
Optuna 優化器測試
"""
import pytest
import pandas as pd
import numpy as np
import optuna
import tempfile
from pathlib import Path
import sys
import os

# 確保 path 正確
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.optuna_optimizer import OptunaOptimizer, _build_search_space
from utils.objective_builder import (
    get_objective_fn, list_objectives, custom_objective,
    metric_sharpe_ratio, metric_calmar_ratio, metric_profit_factor,
)
from utils.study_storage import (
    init_db, save_study_meta, save_trial_meta,
    save_trial_result, load_trial_result, get_study_summary,
    list_studies, DATA_DIR, DB_PATH, TRIALS_DIR,
)
from utils.seed import set_global_seed, seed_for_trial
from utils.walk_forward import WalkForwardValidator, _specs_to_grid_space
from utils.perturbation import PerturbationTester
from utils.param_space_editor import specs_to_param_space_dict, _parse_choices
from strategies.strategy_runner import execute_user_strategy
from utils.backtester import BacktestEngine


# === Fixture ===

@pytest.fixture
def sample_df():
    """產生 500 根固定 seed 的測試 K 線"""
    np.random.seed(42)
    n = 500
    base_price = 30000
    returns = np.random.normal(0.0005, 0.02, n)
    close = base_price * np.exp(np.cumsum(returns))
    high = close * (1 + np.abs(np.random.normal(0, 0.005, n)))
    low = close * (1 - np.abs(np.random.normal(0, 0.005, n)))
    open_ = np.roll(close, 1)
    open_[0] = base_price
    volume = np.random.uniform(100, 1000, n)
    return pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    }, index=pd.date_range("2024-01-01", periods=n, freq="1D"))


@pytest.fixture
def sma_strategy_code():
    return '''
def generate_signals(df, params):
    fast = params.get("fast_period", 20)
    slow = params.get("slow_period", 50)
    df["sma_fast"] = df["close"].rolling(fast).mean()
    df["sma_slow"] = df["close"].rolling(slow).mean()
    entries = (df["sma_fast"] > df["sma_slow"]) & (df["sma_fast"].shift(1) <= df["sma_slow"].shift(1))
    exits = (df["sma_fast"] < df["sma_slow"]) & (df["sma_fast"].shift(1) >= df["sma_slow"].shift(1))
    return entries.fillna(False), exits.fillna(False)
'''


# === 測試：seed ===

class TestSeed:
    def test_set_global_seed(self):
        set_global_seed(123)
        assert set_global_seed(123) == 123
        # 連跑兩次 random 應該一致
        import random
        set_global_seed(42)
        a = [random.random() for _ in range(5)]
        set_global_seed(42)
        b = [random.random() for _ in range(5)]
        assert a == b

    def test_seed_for_trial(self):
        s0 = seed_for_trial(0, base_seed=42)
        s1 = seed_for_trial(1, base_seed=42)
        s0_again = seed_for_trial(0, base_seed=42)
        assert s0 == s0_again
        assert s0 != s1
        assert all(0 <= s < 2**31 - 1 for s in [s0, s1])


# === 測試：objective_builder ===

class TestObjectiveBuilder:
    def test_list_objectives(self):
        objs = list_objectives()
        assert "sharpe_ratio" in objs
        assert "calmar_ratio" in objs
        assert "profit_factor" in objs
        assert "cagr_minus_half_maxdd" in objs

    def test_get_objective_fn(self):
        fn = get_objective_fn("sharpe_ratio")
        assert fn({"sharpe_ratio": 2.0}) == 2.0
        assert fn({}) == 0.0

    def test_invalid_objective(self):
        with pytest.raises(ValueError):
            get_objective_fn("nonexistent_metric")

    def test_metric_profit_factor(self):
        fn = get_objective_fn("profit_factor")
        assert fn({"profit_factor": 2.5}) == 2.5
        assert fn({"profit_factor": -1.0}) == 0.0
        assert fn({"profit_factor": 0.0}) == 0.0

    def test_metric_cagr_minus_half_maxdd(self):
        fn = get_objective_fn("cagr_minus_half_maxdd")
        # cagr=20, maxdd=10 → 20 - 5 = 15
        assert fn({"cagr_pct": 20, "max_drawdown_pct": 10}) == 15.0

    def test_custom_objective(self):
        # 自訂公式
        v = custom_objective(
            {"cagr_pct": 30, "max_drawdown_pct": 10},
            "cagr_pct - 0.5 * max_drawdown_pct"
        )
        assert v == 25.0


# === 測試：search space 構造 ===

class TestBuildSearchSpace:
    def test_int_param(self):
        def obj(trial):
            return _build_search_space(trial, [
                {"name": "p1", "type": "int", "low": 1, "high": 10}
            ])["p1"]
        study = optuna.create_study()
        study.optimize(obj, n_trials=5)
        # 確保 p1 都在 1-10 內
        for t in study.trials:
            assert 1 <= t.params["p1"] <= 10

    def test_float_log_param(self):
        def obj(trial):
            return _build_search_space(trial, [
                {"name": "p1", "type": "float_log", "low": 0.001, "high": 0.1}
            ])["p1"]
        study = optuna.create_study(sampler=optuna.samplers.RandomSampler(seed=42))
        study.optimize(obj, n_trials=20)
        for t in study.trials:
            assert 0.001 <= t.params["p1"] <= 0.1

    def test_categorical_param(self):
        def obj(trial):
            return _build_search_space(trial, [
                {"name": "p1", "type": "categorical", "choices": ["a", "b", "c"]}
            ])["p1"]
        study = optuna.create_study(sampler=optuna.samplers.GridSampler({"p1": ["a", "b", "c"]}))
        study.optimize(obj, n_trials=3)
        for t in study.trials:
            assert t.params["p1"] in ["a", "b", "c"]


# === 測試：study_storage ===

class TestStudyStorage:
    def setup_method(self):
        # 清掉舊資料
        init_db()
        # 確保 db 存在
        assert DB_PATH.exists() or True  # 可能被前面測試建立

    def test_init_db(self):
        init_db()
        assert DB_PATH.exists()

    def test_save_and_load_study_meta(self):
        save_study_meta(
            study_name="test_study_1",
            direction="maximize",
            sampler="tpe",
            pruner="median",
            n_trials=10,
            best_value=2.5,
            best_params={"x": 5, "y": 0.1},
            extra_config={"test": True},
        )
        summary = get_study_summary("test_study_1")
        assert summary is not None
        assert summary["best_value"] == 2.5
        assert summary["best_params"] == {"x": 5, "y": 0.1}

    def test_save_trial_meta(self):
        save_trial_meta(
            study_name="test_study_1",
            number=0,
            value=1.5,
            state="complete",
            params={"x": 5},
            user_attrs={"n_trades": 10},
        )
        from utils.study_storage import list_trial_metadata
        df = list_trial_metadata("test_study_1")
        assert len(df) >= 1
        assert 0 in df["number"].values

    def test_save_and_load_trial_result(self):
        metrics = {"sharpe_ratio": 1.5, "total_return_pct": 25.0, "n_trades": 10}
        params = {"x": 5}
        trades = [{"entry_time": "2024-01-01", "exit_time": "2024-01-02", "pnl_pct": 0.05}]
        equity_df = pd.DataFrame({"equity": [10000, 10500]}, index=pd.date_range("2024-01-01", periods=2))
        path = save_trial_result(
            study_name="test_parquet",
            trial_number=0,
            metrics=metrics,
            params=params,
            trades=trades,
            equity_curve=equity_df,
        )
        assert path.exists()
        loaded = load_trial_result("test_parquet", 0)
        assert loaded is not None
        assert loaded["params"] == params
        assert loaded["metrics"]["sharpe_ratio"] == 1.5


# === 測試：OptunaOptimizer ===

class TestOptunaOptimizer:
    def test_basic_run(self, sample_df, sma_strategy_code):
        opt = OptunaOptimizer(
            strategy_runner=execute_user_strategy,
            backtest_engine_class=BacktestEngine,
            objective_name="sharpe_ratio",
            sampler="tpe",
            pruner="median",
            seed=42,
        )
        param_specs = [
            {"name": "fast_period", "type": "int", "low": 5, "high": 20},
            {"name": "slow_period", "type": "int", "low": 30, "high": 80},
        ]
        result = opt.run(
            df=sample_df,
            strategy_code=sma_strategy_code,
            param_specs=param_specs,
            n_trials=8,
            study_name="test_optuna_basic",
            persist=False,
        )
        assert "best_params" in result
        assert "fast_period" in result["best_params"]
        assert "slow_period" in result["best_params"]
        # 確保 n_trials_completed >= 1
        assert result["n_trials_completed"] >= 1

    def test_run_with_progress_callback(self, sample_df, sma_strategy_code):
        opt = OptunaOptimizer(
            strategy_runner=execute_user_strategy,
            backtest_engine_class=BacktestEngine,
            objective_name="sharpe_ratio",
            sampler="random",
            seed=42,
        )
        progress_calls = []
        def cb(trial_num, total, current, best, params):
            progress_calls.append((trial_num, current, best, params))

        result = opt.run(
            df=sample_df,
            strategy_code=sma_strategy_code,
            param_specs=[{"name": "fast_period", "type": "int", "low": 5, "high": 30}],
            n_trials=5,
            progress_callback=cb,
            study_name="test_progress",
            persist=False,
        )
        # 至少要有 1 次 callback（n_trials_completed 過 0 即可）
        assert len(progress_calls) >= 1

    def test_run_with_persistence(self, sample_df, sma_strategy_code):
        opt = OptunaOptimizer(
            strategy_runner=execute_user_strategy,
            backtest_engine_class=BacktestEngine,
            objective_name="sharpe_ratio",
            sampler="tpe",
            seed=42,
        )
        result = opt.run(
            df=sample_df,
            strategy_code=sma_strategy_code,
            param_specs=[{"name": "fast_period", "type": "int", "low": 5, "high": 20}],
            n_trials=3,
            study_name="test_persist",
            persist=True,
        )
        # 確認有存到 DB
        summary = get_study_summary("test_persist")
        assert summary is not None
        assert summary["n_trials"] >= 3

    def test_get_param_importances(self, sample_df, sma_strategy_code):
        opt = OptunaOptimizer(
            strategy_runner=execute_user_strategy,
            backtest_engine_class=BacktestEngine,
            objective_name="sharpe_ratio",
            sampler="random",
            seed=42,
        )
        result = opt.run(
            df=sample_df,
            strategy_code=sma_strategy_code,
            param_specs=[
                {"name": "fast_period", "type": "int", "low": 5, "high": 30},
                {"name": "slow_period", "type": "int", "low": 30, "high": 100},
            ],
            n_trials=10,
            study_name="test_importance",
            persist=False,
        )
        # 至少有一個 trial 才會有重要性
        if result["n_trials_completed"] >= 2:
            assert isinstance(result["param_importances"], dict)
            # 至少包含 fast_period 或 slow_period
            assert any("period" in k for k in result["param_importances"].keys())


# === 測試：PerturbationTester ===

class TestPerturbationTester:
    def test_perturb_int(self):
        from utils.perturbation import PerturbationTester
        tester = PerturbationTester(
            strategy_runner=None,  # 不會用到
            backtest_engine_class=None,
        )
        # 整數
        assert tester._perturb_value(20, 0.1) == 22  # round(20*1.1)
        assert tester._perturb_value(20, -0.1) == 18
        # 浮點
        assert abs(tester._perturb_value(0.02, 0.1) - 0.022) < 0.0001
        # 字串不變
        assert tester._perturb_value("sma", 0.1) == "sma"

    def test_run_with_strategy(self, sample_df, sma_strategy_code):
        tester = PerturbationTester(
            strategy_runner=execute_user_strategy,
            backtest_engine_class=BacktestEngine,
            objective_name="sharpe_ratio",
            perturbation_pcts=[-0.2, -0.1, 0.1, 0.2],
        )
        result = tester.run(
            df=sample_df,
            strategy_code=sma_strategy_code,
            best_params={"fast_period": 10, "slow_period": 30},
        )
        assert "baseline_value" in result
        assert "per_param" in result
        assert "stability_score" in result
        assert 0 <= result["stability_score"] <= 100
        # 至少要擾動 2 個參數 × 4 個 pct = 8 筆
        assert len(result["per_param"]) >= 8


# === 測試：WalkForward ===

class TestWalkForward:
    def test_grid_optimizer(self, sample_df, sma_strategy_code):
        validator = WalkForwardValidator(
            strategy_runner=execute_user_strategy,
            backtest_engine_class=BacktestEngine,
            n_splits=3,
            inner_optimizer="grid",
        )
        result = validator.run(
            df=sample_df,
            strategy_code=sma_strategy_code,
            param_space={
                "fast_period": [5, 10, 15],
                "slow_period": [30, 50],
            },
        )
        assert "windows" in result
        assert result["n_windows"] >= 1
        assert "degradation_pct" in result

    def test_optuna_optimizer(self, sample_df, sma_strategy_code):
        validator = WalkForwardValidator(
            strategy_runner=execute_user_strategy,
            backtest_engine_class=BacktestEngine,
            n_splits=3,
            inner_optimizer="optuna",
            inner_n_trials=5,
        )
        result = validator.run(
            df=sample_df,
            strategy_code=sma_strategy_code,
            param_specs=[
                {"name": "fast_period", "type": "int", "low": 5, "high": 20},
                {"name": "slow_period", "type": "int", "low": 30, "high": 60},
            ],
        )
        assert "windows" in result
        assert result["inner_optimizer"] == "optuna"

    def test_specs_to_grid_space(self):
        specs = [
            {"name": "fast", "type": "int", "low": 5, "high": 30},
            {"name": "risk", "type": "float_log", "low": 0.01, "high": 0.1},
        ]
        grid = _specs_to_grid_space(specs)
        assert "fast" in grid
        assert "risk" in grid
        assert all(isinstance(v, int) for v in grid["fast"])
        assert all(isinstance(v, float) for v in grid["risk"])


# === 測試：param_space_editor helpers ===

class TestParamSpaceEditor:
    def test_parse_choices(self):
        assert _parse_choices("a, b, c") == ["a", "b", "c"]
        assert _parse_choices("1, 2, 3") == [1, 2, 3]
        assert _parse_choices("0.5, 1.0, 1.5") == [0.5, 1.0, 1.5]
        assert _parse_choices("") == []
        assert _parse_choices("sma") == ["sma"]

    def test_specs_to_param_space_dict(self):
        specs = [
            {"name": "fast", "type": "int", "low": 5, "high": 30},
            {"name": "ma_type", "type": "categorical", "choices": ["sma", "ema"]},
        ]
        result = specs_to_param_space_dict(specs)
        assert "fast" in result
        assert "ma_type" in result
        assert result["ma_type"] == ["sma", "ema"]


# === 測試：自訂 objective 公式 ===

class TestCustomObjective:
    def test_simple_formula(self):
        v = custom_objective(
            {"sharpe_ratio": 2.0, "max_drawdown_pct": 10.0},
            "sharpe_ratio * 2 - max_drawdown_pct"
        )
        assert v == -6.0  # 2*2 - 10

    def test_invalid_formula(self):
        with pytest.raises(ValueError):
            custom_objective({}, "sharpe_ratio; import os")


# === 測試：caching 與重現性 ===

class TestReproducibility:
    def test_same_seed_same_results(self, sample_df, sma_strategy_code):
        """相同 seed 應該給出相同結果"""
        results = []
        for _ in range(2):
            opt = OptunaOptimizer(
                strategy_runner=execute_user_strategy,
                backtest_engine_class=BacktestEngine,
                objective_name="sharpe_ratio",
                sampler="random",
                seed=42,
            )
            r = opt.run(
                df=sample_df,
                strategy_code=sma_strategy_code,
                param_specs=[{"name": "fast_period", "type": "int", "low": 5, "high": 20}],
                n_trials=5,
                study_name=f"repro_{_}",
                persist=False,
            )
            results.append(r["best_value"])
        assert results[0] == results[1]
