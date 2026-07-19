"""
save_backtest.py — 把有價值的回測結果永久化到 backtest_history/ + git 跟踪。
用法：
  python3 save_backtest.py <task_id> [strategy_name] [symbol] [timeframe]
或作為函數被 run_backtest_perm.py 調用。
判定「有價值」：Sharpe>=0.3 或 總回報>=10% 或 (勝率>=55% 且 交易>=20)
"""
from __future__ import annotations
import os, sys, json, subprocess, datetime, requests

ROOT = os.path.abspath(os.path.dirname(__file__))
HIST = os.path.join(ROOT, "backtest_history")
API = os.getenv("BACKEND_URL", "https://affectionate-alignment-production-6d7e.up.railway.app/api")
TOKEN = os.getenv("ADMIN_TOKEN", "")


def _valuable(m: dict) -> bool:
    sharpe = float(m.get("sharpe_ratio") or 0)
    ret = float(m.get("total_return_pct") or 0)
    win = float(m.get("win_rate") or 0)
    trades = int(m.get("total_trades") or 0)
    return (sharpe >= 0.3) or (ret >= 10.0) or (win >= 55.0 and trades >= 20)


def fetch(task_id: str) -> dict | None:
    H = {"Authorization": f"Bearer {TOKEN}"}
    r = requests.get(f"{API}/backtest/results/{task_id}", headers=H, timeout=20)
    if r.status_code != 200:
        return None
    return r.json()


def save(task_id: str, strategy: str = "unknown", symbol: str = "BTC/USDT",
         timeframe: str = "1d") -> str | None:
    d = fetch(task_id)
    if not d:
        print(f"[skip] {task_id} 無結果")
        return None
    m = d.get("metrics") or d.get("result", {}).get("metrics", {})
    if not _valuable(m):
        print(f"[skip] {task_id} 不達永久門檻: Sharpe={m.get('sharpe_ratio')} ret={m.get('total_return_pct')}% win={m.get('win_rate')}%")
        return None
    os.makedirs(HIST, exist_ok=True)
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    fname = f"{strategy}_{symbol.replace('/','')}_{timeframe}_{date}.json"
    fpath = os.path.join(HIST, fname)
    # 附加元數據
    payload = {"_meta": {"strategy": strategy, "symbol": symbol, "timeframe": timeframe,
                         "saved_at": datetime.datetime.now().isoformat(), "task_id": task_id},
               "metrics": m}
    with open(fpath, "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    # git 永久化
    subprocess.run(["git", "add", "backtest_history/"], cwd=ROOT, check=False)
    subprocess.run(["git", "commit", "-q", "-m",
                    f"perf: 永久保存回測 {strategy} {symbol} {timeframe} ({date})"],
                   cwd=ROOT, check=False)
    subprocess.run(["git", "push", "origin", "master"], cwd=ROOT, check=False)
    print(f"[saved] {fname} → backtest_history/ (git 已提交)")
    return fpath


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python3 save_backtest.py <task_id> [strategy] [symbol] [tf]")
        sys.exit(1)
    save(sys.argv[1], *(sys.argv[2:5] if len(sys.argv) > 2 else []))
