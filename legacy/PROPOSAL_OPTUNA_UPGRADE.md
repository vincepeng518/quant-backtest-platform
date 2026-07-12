# Optuna 升級計劃

## 目標
把現有 Grid Search / Random Search 升級成以 **Optuna Bayesian Optimization** 為主的多模式優化系統。

## 設計

### 新增檔案
- `utils/seed.py` - 隨機種子管理（可重現性）
- `utils/study_storage.py` - SQLite + Parquet 持久化
- `utils/objective_builder.py` - 目標函數（sharpe/calmar/profit_factor/cagr-max_dd）
- `utils/param_space_editor.py` - 範圍型參數編輯器（int/float/categorical/log）
- `utils/optuna_optimizer.py` - Optuna 核心（TPE + MedianPruner）
- `utils/perturbation.py` - 最佳參數穩定性測試
- `utils/param_importance.py` - 參數重要性分析（fANOVA）

### 修改檔案
- `utils/walk_forward.py` - 支援 Optuna + TimeSeriesSplit
- `app.py` - UI 切換（Grid / Bayesian）+ Bayesian 模式 UI
- `requirements.txt` - optuna, plotly-optuna

## 流程

1. 計劃（plan.md）— 給用戶看
2. 核心模組（objective / param_space_editor / optuna_optimizer / storage / seed）
3. 增強（walk_forward 用 Optuna / perturbation / param_importance）
4. UI 整合（app.py）
5. 測試（test_optuna_optimizer.py / test_objective_builder.py / test_storage.py）
6. 端到端 Playwright 驗證
7. Commit + Push

## UI 設計

### 自動參數優化
- 新增「優化模式」radio：Grid / Bayesian
- Bayesian 模式：參數空間用「名稱 + 範圍 + 型態」格式
  - 例：`fast_period: int 5~50`
  - 例：`risk_pct: float 0.005~0.03 (log)`
  - 例：`ma_type: categorical [sma, ema]`
- 新增「目標函數」selectbox：Sharpe / Calmar / Profit Factor / CAGR-0.5*MaxDD / Custom
- 進度條 + 最佳參數即時更新
- Top 10 比較表
- 參數重要性圖
- 擾動測試結果

### 持久化
- `data/optuna_studies.db` (SQLite) - 所有 study
- `data/trials/{study_name}_{trial_id}.parquet` - 每個 trial 的權益曲線

## 目標函數範例

```python
def objective(trial):
    fast = trial.suggest_int("fast_period", 5, 50)
    slow = trial.suggest_int("slow_period", 30, 200)
    risk_pct = trial.suggest_float("risk_pct", 0.005, 0.03, log=True)

    params = {**fixed_params, "fast_period": fast, "slow_period": slow, "risk_pct": risk_pct}

    # 跑回測
    result = run_backtest(...)
    if result has error or n_trades < 5:
        raise optuna.TrialPruned()

    # 計算目標指標
    return calculate_metric(result, objective_name="sharpe_ratio")
```
