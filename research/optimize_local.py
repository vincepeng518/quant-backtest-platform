"""
optimize_local.py — 純本地：參數優化 → WF → 蒙特卡洛 → 永久化。
不經 Railway API（本地 venv + engine 直接跑，快且穩）。
用法：
  python3 optimize_local.py <strategy_py> [csv_path] [n_windows=5] [n_sims=1000]
流程：
  1. 載入策略類 + 參數空間 (get_params_space)
  2. Optimizer.grid_search 找 best_params (用 Sharpe 最大化)
  3. WalkForwardAnalyzer 滾動驗證 (IS 優化 / OOS 測試) → avg_oos_sharpe / consistency
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
from engine.analyzer import WalkForwardAnalyzer, MonteCarloSimulator
from strategies.base import StrategyBase


def load_strategy(py_path: str):
    py_path = os.path.abspath(py_path)
    spec = importlib.util.spec_from_file_location("__tmp_mod", py_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cls = [c for c in mod.__dict__.values()
           if isinstance(c, type) and issubclass(c, StrategyBase) and c is not StrategyBase]
    return cls[0]


def load_csv(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    # 兼容欄位名
    ren = {}
    for col in df.columns:
        cl = col.lower()
        if cl in ("timestamp", "time", "date", "open_time"):
            ren[col] = "timestamp"
        elif cl in ("open", "o"):
            ren[col] = "open"
        elif cl in ("high", "h"):
            ren[col] = "high"
        elif cl in ("low", "l"):
            ren[col] = "low"
        elif cl in ("close", "c"):
            ren[col] = "close"
        elif cl in ("volume", "vol", "v"):
            ren[col] = "volume"
    df = df.rename(columns=ren)
    if "timestamp" not in df.columns:
        df["timestamp"] = pd.date_range("2018-01-01", periods=len(df), freq="1d")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


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

    ps = cls.get_params_space()
    # 轉成 Optimizer 的 param_space 格式 (choice), 限制總組合 <= MAX_COMBOS
    MAX_COMBOS = 80
    n_params = len(ps)
    n_pts = max(3, int(MAX_COMBOS ** (1.0 / n_params)))  # 每參數點數 (>=3 避免太粗)
    space = {}
    for k, v in ps.items():
        mn, mx = float(v["min"]), float(v["max"])
        is_int = v.get("type") == "int"
        if is_int:
            step = max(1.0, (mx - mn) / (n_pts - 1))
            pts = [int(round(mn + i * step)) for i in range(n_pts)]
        else:
            step = (mx - mn) / (n_pts - 1)
            pts = [mn + i * step for i in range(n_pts)]
        space[k] = {"type": "choice", "values": pts}
    total = 1
    for v in space.values():
        total *= len(v["values"])
    print(f"  grid combos={total} (capped at {MAX_COMBOS})")

    bt = Backtester()
    bt.set_data(df)
    bt.set_strategy(cls())  # 必須先 set_strategy 否則 grid_search 內 strategy=None 全部 score=0
    opt = Optimizer(bt, metric="sharpe_ratio", maximize=True)
    t0 = time.time()
    results = opt.grid_search(space, max_workers=4)
    best = results[0]["params"]
    best_score = results[0]["score"]
    print(f"  best={best} score={best_score:.3f} ({time.time()-t0:.0f}s)")

    # 用 best 跑一次完整回測拿 equity_curve
    bt.set_strategy(cls())
    bt.strategy.init(best)
    full = bt.run()
    print(f"  full: Sharpe={full.sharpe_ratio:.3f} ret={full.total_return_pct:.2f}% trades={full.total_trades}")

    print(f"[3] walk-forward (n_windows={n_windows})")
    wf = WalkForwardAnalyzer(bt)
    wf_res = wf.analyze(df, cls, space, n_windows=n_windows, opt_method="grid")
    print(f"  avg_oos_sharpe={wf_res.get('avg_oos_sharpe'):.3f} consistency={wf_res.get('consistency'):.2f}")

    print(f"[4] monte-carlo (n_sims={n_sims})")
    mc = MonteCarloSimulator(full.equity_curve, n_simulations=n_sims)
    mc_res = mc.simulate(initial_capital=100_000)
    # 移除 paths (1000條路徑, 6.9MB) 只留統計量
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
    fname = f"opt_{name}_{date}.json"
    fpath = os.path.join(hist_dir, fname)
    with open(fpath, "w") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2, default=str)
    subprocess.run(["git", "add", "backtest_history/"], cwd=PROJ, check=False)
    subprocess.run(["git", "commit", "-q", "-m", f"perf: 本地優化+WF+MC {name} {date}"], cwd=PROJ, check=False)
    subprocess.run(["git", "push", "origin", "master"], cwd=PROJ, check=False)
    print(f"  [saved] {fname}")
    print("done.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python3 optimize_local.py <strategy_py> [csv] [n_windows] [n_sims]")
        sys.exit(1)
    main()
