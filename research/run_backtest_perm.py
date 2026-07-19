"""
run_backtest_perm.py — 一條龍：上傳策略 → 跑網站回測 → 等結果 → 自動永久化。
用法：
  python3 run_backtest_perm.py <strategy_py> [symbol=BT/USDT] [timeframe=1d] [source=binance]
會自動呼叫 save_backtest.py 把有價值的結果存進 backtest_history/ + git。
"""
from __future__ import annotations
import os, sys, time, json, requests

ROOT = os.path.abspath(os.path.dirname(__file__))
API = os.getenv("BACKEND_URL", "https://affectionate-alignment-production-6d7e.up.railway.app/api")
TOKEN = os.getenv("ADMIN_TOKEN", "")


def upload(py_path: str) -> str:
    code = open(py_path).read()
    name = os.path.splitext(os.path.basename(py_path))[0]
    H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    r = requests.post(f"{API}/strategy/upload", headers=H,
                       json={"name": name, "description": "auto", "category": "combo", "code": code}, timeout=30)
    if r.status_code != 201:
        raise RuntimeError(f"upload failed {r.status_code} {r.text[:100]}")
    return r.json()["id"]


def run(uid: str, symbol: str, timeframe: str, source: str) -> str:
    H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    cfg = {"strategy": {"template_id": f"user_{uid}"}, "symbol": symbol, "market": "crypto",
           "timeframe": timeframe, "source": source, "initial_capital": 100000.0,
           "commission": 0.001, "engine": "bar"}
    r = requests.post(f"{API}/backtest/run", headers=H, json=cfg, timeout=30)
    if r.status_code != 202:
        raise RuntimeError(f"run failed {r.status_code} {r.text[:100]}")
    return r.json()["task_id"]


def poll(tid: str, wait=60) -> dict | None:
    H = {"Authorization": f"Bearer {TOKEN}"}
    for _ in range(wait):
        d = requests.get(f"{API}/backtest/status/{tid}", headers=H, timeout=15).json()
        st = d.get("status") or d.get("state")
        if st in ("done", "completed", "success"):
            return requests.get(f"{API}/backtest/results/{tid}", headers=H, timeout=15).json()
        if st in ("error", "failed"):
            return {"error": d.get("error") or d.get("detail")}
        time.sleep(5)
    return {"error": "timeout"}


if __name__ == "__main__":
    py = sys.argv[1]
    symbol = sys.argv[2] if len(sys.argv) > 2 else "BTC/USDT"
    tf = sys.argv[3] if len(sys.argv) > 3 else "1d"
    src = sys.argv[4] if len(sys.argv) > 4 else "binance"
    print(f"[1/4] upload {py} ...")
    uid = upload(py)
    print(f"  uid={uid}")
    print(f"[2/4] run backtest {symbol} {tf} ...")
    tid = run(uid, symbol, tf, src)
    print(f"  task={tid}")
    print(f"[3/4] poll ...")
    res = poll(tid)
    if res.get("error"):
        print(f"  ERR: {res['error']}")
        sys.exit(1)
    m = res.get("metrics", {})
    print(f"  => Sharpe={m.get('sharpe_ratio')} ret={m.get('total_return_pct')}% win={m.get('win_rate')}% trades={m.get('total_trades')}")
    print(f"[4/4] save permanent ...")
    name = os.path.splitext(os.path.basename(py))[0]
    sys.path.insert(0, ROOT)
    from save_backtest import save
    save(tid, name, symbol, tf)
    print("done.")
