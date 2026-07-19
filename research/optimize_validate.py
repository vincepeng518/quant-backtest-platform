"""
optimize_validate.py — 一條龍：參數優化 → WF 滾動驗證 → 蒙特卡洛 → 永久化。
用法：
  python3 optimize_validate.py <strategy_py> [symbol=BTC/USDT] [timeframe=1d]
流程：
  1. 上傳策略 → uid
  2. /optimize/run 掃參數空間 → best_params
  3. /analysis/walk-forward 用 best_params 滾動驗證 → OOS sharpe / consistency
  4. /analysis/monte-carlo 用回測 equity 重採樣 → 穩健性
  5. 有價值結果存 backtest_history/ + git
"""
from __future__ import annotations
import os, sys, time, json, requests

ROOT = os.path.abspath(os.path.dirname(__file__))
API = os.getenv("BACKEND_URL", "https://affectionate-alignment-production-6d7e.up.railway.app/api")
TOKEN = os.getenv("ADMIN_TOKEN", "")


def _H():
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def upload(py_path: str) -> str:
    code = open(py_path).read()
    name = os.path.splitext(os.path.basename(py_path))[0]
    r = requests.post(f"{API}/strategy/upload", headers=_H(),
                      json={"name": name, "description": "opt", "category": "combo", "code": code}, timeout=30)
    if r.status_code != 201:
        raise RuntimeError(f"upload {r.status_code} {r.text[:100]}")
    return r.json()["id"]


def _poll_results(endpoint: str, task_id: str, wait=150):
    for _ in range(wait):
        d = requests.get(f"{API}{endpoint}/{task_id}", headers={"Authorization": f"Bearer {TOKEN}"}, timeout=60).json()
        st = d.get("status") or d.get("state")
        if st in ("done", "completed", "success"):
            return d.get("result") or d.get("best_params") or d
        if st in ("error", "failed"):
            return {"error": d.get("error") or d.get("detail")}
        time.sleep(5)
    return {"error": "timeout"}


def optimize(uid: str, param_space: list, symbol: str, tf: str) -> dict:
    cfg = {"strategy_id": f"user_{uid}", "param_space": param_space,
           "algorithm": "grid", "max_trials": 24,
           "symbol": symbol, "timeframe": tf}
    r = requests.post(f"{API}/optimize/run", headers=_H(), json=cfg, timeout=30)
    if r.status_code != 202:
        raise RuntimeError(f"optimize {r.status_code} {r.text[:100]}")
    return _poll_results("/optimize/results", r.json()["task_id"])


def walk_forward(uid: str, best_params: dict, symbol: str, tf: str) -> dict:
    # 把 best_params 轉成 param_space (range, 窄區間)
    ps = []
    for k, v in best_params.items():
        if isinstance(v, (int, float)):
            delta = max(1 if isinstance(v, int) else 0.2, abs(v) * 0.2)
            ps.append({"name": k, "min": v - delta, "max": v + delta,
                       "step": 1 if isinstance(v, int) else 0.1})
    cfg = {"strategy_id": f"user_{uid}", "param_space": ps,
           "symbol": symbol, "timeframe": tf, "n_windows": 5, "algorithm": "grid"}
    r = requests.post(f"{API}/analysis/walk-forward", headers=_H(), json=cfg, timeout=30)
    if r.status_code != 202:
        raise RuntimeError(f"wf {r.status_code} {r.text[:100]}")
    return _poll_results("/analysis/results", r.json()["task_id"])


def monte_carlo(equity_curve: list, n_sim=1000) -> dict:
    cfg = {"equity_curve": equity_curve, "n_simulations": n_sim}
    r = requests.post(f"{API}/analysis/monte-carlo", headers=_H(), json=cfg, timeout=30)
    if r.status_code != 202:
        raise RuntimeError(f"mc {r.status_code} {r.text[:100]}")
    return _poll_results("/analysis/results", r.json()["task_id"])


def save_report(name: str, symbol: str, tf: str, opt: dict, wf: dict, mc: dict):
    os.makedirs(os.path.join(ROOT, "backtest_history"), exist_ok=True)
    date = time.strftime("%Y-%m-%d")
    rep = {
        "_meta": {"strategy": name, "symbol": symbol, "timeframe": tf, "date": date},
        "optimize": opt, "walk_forward": wf, "monte_carlo": mc,
    }
    fname = f"opt_{name}_{symbol.replace('/','')}_{tf}_{date}.json"
    fpath = os.path.join(ROOT, "backtest_history", fname)
    with open(fpath, "w") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    import subprocess
    subprocess.run(["git", "add", "backtest_history/"], cwd=ROOT, check=False)
    subprocess.run(["git", "commit", "-q", "-m", f"perf: 參數優化+WF+MC {name} {date}"], cwd=ROOT, check=False)
    subprocess.run(["git", "push", "origin", "master"], cwd=ROOT, check=False)
    print(f"[saved] {fname}")


if __name__ == "__main__":
    py = sys.argv[1]
    symbol = sys.argv[2] if len(sys.argv) > 2 else "BTC/USDT"
    tf = sys.argv[3] if len(sys.argv) > 3 else "1d"
    py = os.path.abspath(py)
    name = os.path.splitext(os.path.basename(py))[0]
    print(f"[1] upload {py}")
    uid = upload(py)
    print(f"  uid={uid}")
    # 參數空間從策略 get_params_space 讀 (local import)
    sys.path.insert(0, os.path.dirname(ROOT))  # 專案根 (strategies/ 在這)
    import importlib.util
    spec = importlib.util.spec_from_file_location("__tmp_mod", py)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from strategies.base import StrategyBase
    cls = [c for c in mod.__dict__.values() if isinstance(c, type) and issubclass(c, StrategyBase) and c is not StrategyBase and hasattr(c, "get_params_space")]
    ps = list(cls[0].get_params_space().items())
    param_space = [{"name": k, **v} for k, v in ps]
    print(f"[2] optimize ({len(param_space)} params)")
    opt = optimize(uid, param_space, symbol, tf)
    if opt.get("error"):
        print("  OPT ERR:", opt["error"]); sys.exit(1)
    best = opt.get("best_params") or (opt.get("trials", [{}])[0].get("params", {}))
    print(f"  best_params={best}")
    print(f"[3] walk-forward (OOS validation)")
    wf = walk_forward(uid, best, symbol, tf)
    if wf.get("error"):
        print("  WF ERR:", wf["error"])
    else:
        print(f"  avg_oos_sharpe={wf.get('avg_oos_sharpe')} consistency={wf.get('consistency')}")
    print(f"[4] monte-carlo")
    # equity_curve 從優化最佳回測拿 (若有)
    eq = opt.get("best_equity") or opt.get("equity_curve")
    mc = monte_carlo(eq, 1000) if eq else {"skipped": "no equity"}
    if mc.get("error"):
        print("  MC ERR:", mc["error"])
    else:
        print(f"  expected_return={mc.get('expected_return')} return_std={mc.get('return_std')}")
    print(f"[5] save permanent")
    save_report(name, symbol, tf, opt, wf, mc)
    print("done.")
