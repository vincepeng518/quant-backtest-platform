"""
optimize_local.py — 純本地：參數優化 → WF → 蒙特卡洛 → 永久化。
不經 Railway API（本地 venv + engine 直接跑，快且穩）。
用法：
  python3 optimize_local.py <strategy_py> [csv_path] [n_windows=5] [n_sims=1000]
流程：
  1. 載入策略類 + 參數空間 (get_params_space)
  2. Optimizer.bayesian_optimization 找 best_params (Sharpe 最大化, ~25 評估)
  3. 手寫 Walk-Forward 用 best_params 滾窗測 OOS 穩健性
  4. MonteCarloSimulator 用 equity_curve 重採樣 → 穩健性
  5. 結果存 backtest_history/ + git
"""
from __future__ import annotations
import os, sys, time, json, importlib.util, subprocess, datetime
import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(ROOT))  # 專案根 (strategies/, engine/, data/)
from engine.backtester import Backtester
from engine.optimizer import Optimizer
from engine.analyzer import MonteCarloSimulator
from strategies.base import StrategyBase


def load_strategy(py_path: str):
    py_path = os.path.abspath(py_path)
    spec = importlib.util.spec_from_file_location("__tmp_mod", py_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for attr in dir(mod):
        obj = getattr(mod, attr)
        if isinstance(obj, type) and issubclass(obj, StrategyBase) and obj is not StrategyBase:
            return obj
    raise RuntimeError(f"no StrategyBase subclass found in {py_path}")


def load_csv(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df = df.rename(columns={c: c.lower() for c in df.columns})
    for col in ("open", "high", "low", "close", "volume"):
        if col not in df.columns and col.capitalize() in df.columns:
            df[col] = df[col.capitalize()]
    return df


def _space_from_ps(ps: dict, n_pts: int = 3) -> dict:
    """把 get_params_space() 轉成 Optimizer 接受的格式 (備用)。

    策略直接回傳 {'min'/'max'/'step' (range) 或 'values' (choice)} 的格式,
    Optimizer 原生就認得, 故這裡基本直透。"""
    space: dict = {}
    for k, v in ps.items():
        if "values" in v:
            space[k] = {"type": "choice", "values": list(v["values"])}
        elif "min" in v and "max" in v:
            space[k] = {
                "type": "range",
                "min": float(v["min"]),
                "max": float(v["max"]),
                "step": float(v.get("step", 1)),
            }
    return space


def _walk_forward_oos(df: pd.DataFrame, cls, best: dict, ps: dict, n_windows: int) -> dict:
    """真正 Walk-Forward: 每段用前面 IS 數據重優化, 測接下來 OOS 段 (非複用樣本內 best)。

    切 n_windows 段。對 i in 1..n_windows-1:
      IS = df[0 : i*win]  (前面所有), 在該 IS 上優化 best_i
      OOS = df[i*win : (i+1)*win], 用 best_i 測
    這樣 OOS 參數來自獨立 IS, 不泄露。
    """
    n = len(df)
    win = n // n_windows
    if win < 50:
        # 數據太少, 退回單次 (仍用 is 前半優化)
        half = n // 2
        is_df, oos_df = df.iloc[:half], df.iloc[half:]
        best_i = _optimize_params(is_df, cls, ps)
        return _eval_oos([(is_df, oos_df, best_i)], cls, n_windows)
    oos_sharpes, oos_returns, oos_dds = [], [], []
    windows = []
    for i in range(1, n_windows):
        is_df = df.iloc[: i * win]
        oos_df = df.iloc[i * win : (i + 1) * win]
        if len(is_df) < 30 or len(oos_df) < 5:
            continue
        best_i = _optimize_params(is_df, cls, ps)
        bt = Backtester()
        bt.set_data(oos_df)
        s = cls()
        s.init(best_i)
        bt.set_strategy(s)
        try:
            r = bt.run()
            oos_sharpes.append(r.sharpe_ratio)
            oos_returns.append(r.total_return_pct)
            oos_dds.append(r.max_drawdown_pct)
            # 記錄該窗用的 IS 區間
            windows.append({"is_range": f"0..{i*win}", "oos_range": f"{i*win}..{(i+1)*win}",
                            "oos_sharpe": r.sharpe_ratio, "oos_return": r.total_return_pct,
                            "oos_max_dd": r.max_drawdown_pct})
        except Exception:
            continue
    if not oos_sharpes:
        return {"avg_oos_sharpe": 0.0, "avg_oos_return": 0.0, "sharpe_std": 0.0,
                "return_std": 0.0, "consistency": 0.0, "windows": []}
    arr = np.array(oos_sharpes)
    pos = (arr > 0).sum()
    return {
        "avg_oos_sharpe": float(arr.mean()),
        "avg_oos_return": float(np.mean(oos_returns)),
        "sharpe_std": float(arr.std()),
        "return_std": float(np.std(oos_returns)),
        "consistency": float(pos / len(arr)),
        "windows": windows,
    }


def _optimize_params(is_df: pd.DataFrame, cls, ps: dict) -> dict:
    """在 IS 數據上用 Bayesian 優化找 best params (輕量: 減少 iter 加速 WF)。"""
    bt = Backtester()
    bt.set_data(is_df)
    bt.set_strategy(cls())
    opt = Optimizer(bt, metric="sharpe_ratio", maximize=True)
    try:
        res = opt.bayesian_optimization(ps, n_iterations=8, n_initial=6)
        return res[0]["params"]
    except Exception:
        return {}


def _eval_oos(pairs, cls, n_windows):
    oos_sharpes, oos_returns, oos_dds, windows = [], [], [], []
    for is_df, oos_df, best_i in pairs:
        bt = Backtester()
        bt.set_data(oos_df)
        s = cls()
        s.init(best_i)
        bt.set_strategy(s)
        try:
            r = bt.run()
            oos_sharpes.append(r.sharpe_ratio)
            oos_returns.append(r.total_return_pct)
            oos_dds.append(r.max_drawdown_pct)
            windows.append({"oos_sharpe": r.sharpe_ratio, "oos_return": r.total_return_pct,
                            "oos_max_dd": r.max_drawdown_pct})
        except Exception:
            continue
    if not oos_sharpes:
        return {"avg_oos_sharpe": 0.0, "avg_oos_return": 0.0, "sharpe_std": 0.0,
                "return_std": 0.0, "consistency": 0.0, "windows": []}
    arr = np.array(oos_sharpes)
    return {
        "avg_oos_sharpe": float(arr.mean()),
        "avg_oos_return": float(np.mean(oos_returns)),
        "sharpe_std": float(arr.std()),
        "return_std": float(np.std(oos_returns)),
        "consistency": float((arr > 0).sum() / len(arr)),
        "windows": windows,
    }


def main():
    py = sys.argv[1]
    csv_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "..", "data", "csv", "BTC_USDT.csv")
    n_windows = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    n_sims = int(sys.argv[4]) if len(sys.argv) > 4 else 1000

    name = os.path.splitext(os.path.basename(py))[0]
    print(f"[1] load {name}")
    cls = load_strategy(py)
    df = load_csv(csv_path)
    print(f"  bars={len(df)}, cols={list(df.columns)}")

    ps = cls().get_params_space()
    print(f"  params={list(ps.keys())} (bayesian ~25 eval)")

    bt = Backtester()
    bt.set_data(df)
    bt.set_strategy(cls())  # 必須先 set_strategy 否則 grid_search 內 strategy=None 全部 score=0
    opt = Optimizer(bt, metric="sharpe_ratio", maximize=True)
    t0 = time.time()
    results = opt.bayesian_optimization(ps, n_iterations=15, n_initial=10)
    best = results[0]["params"]
    best_score = results[0]["score"]
    print(f"  best={best} score={best_score:.3f} ({time.time()-t0:.0f}s)")

    # 用 best 跑一次完整回測拿 equity_curve
    bt.set_strategy(cls())
    bt.strategy.init(best)
    full = bt.run()
    print(f"  full: Sharpe={full.sharpe_ratio:.3f} ret={full.total_return_pct:.2f}% trades={full.total_trades}")

    print(f"[3] walk-forward (n_windows={n_windows}, TRUE rolling IS-optimize -> OOS)")
    wf_res = _walk_forward_oos(df, cls, best, ps, n_windows)
    print(f"  avg_oos_sharpe={wf_res.get('avg_oos_sharpe'):.3f} consistency={wf_res.get('consistency'):.2f}")

    print(f"[4] monte-carlo (n_sims={n_sims})")
    mc = MonteCarloSimulator(full.equity_curve, n_simulations=n_sims)
    mc_res = mc.simulate(initial_capital=100_000)
    mc_res.pop("paths", None)
    print(f"  expected_return={mc_res.get('expected_return'):.3f} return_std={mc_res.get('return_std'):.3f}")

    print(f"[5] save permanent")
    PROJ = os.path.dirname(ROOT)  # 專案根 (/root/Crypto-Backtesting-Lab)
    hist_dir = os.path.join(PROJ, "backtest_history")
    os.makedirs(hist_dir, exist_ok=True)
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    rep = {
        "_meta": {"strategy": name, "csv": os.path.basename(csv_path),
                  "date": date, "n_windows": n_windows, "n_sims": n_sims},
        "best_params": best, "best_score": best_score,
        "full_backtest": {"sharpe": full.sharpe_ratio, "total_return_pct": full.total_return_pct,
                          "max_drawdown_pct": full.max_drawdown_pct, "win_rate": full.win_rate,
                          "total_trades": full.total_trades},
        "walk_forward": wf_res,
        "monte_carlo": mc_res,
    }
    fname = f"opt_{name}_{os.path.splitext(os.path.basename(csv_path))[0]}_{date}.json"
    fpath = os.path.join(hist_dir, fname)
    with open(fpath, "w") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2, default=str)
    # NO_PUSH: 完全不做任何 git 操作 (add/commit/push 全跳過)，避免並行時 index 競爭
    if not os.environ.get("NO_PUSH"):
        subprocess.run(["git", "add", "backtest_history/"], cwd=PROJ, check=False)
        subprocess.run(["git", "commit", "-q", "-m", f"perf: 本地優化+WF+MC {name} {date}"], cwd=PROJ, check=False)
        subprocess.run(["git", "push", "origin", "master"], cwd=PROJ, check=False)
    print(f"  [saved] {fpath}")
    print("done.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python3 optimize_local.py <strategy_py> [csv] [n_windows] [n_sims]")
        sys.exit(1)
    main()
