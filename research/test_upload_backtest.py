"""
test_upload_backtest.py — 驗證「挖到的組合 → 上傳網站 → 跑回測」端到端鏈路。
用法：python3 test_upload_backtest.py <strategy_py_path>
"""
import os, sys, json, time, requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
API = os.getenv("BACKEND_URL", "https://affectionate-alignment-production-6d7e.up.railway.app/api")
TOKEN = os.getenv("ADMIN_TOKEN", "")
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

def upload(py_path):
    code = open(py_path).read()
    # 從 class name 推 name
    name = os.path.splitext(os.path.basename(py_path))[0]
    payload = {"name": name, "description": "combo explorer surprise", "category": "combo", "code": code}
    r = requests.post(f"{API}/strategy/upload", headers=H, json=payload, timeout=30)
    print("upload:", r.status_code, r.text[:200])
    return r.json().get("id") or r.json().get("strategy_id")

def run_backtest(uid, symbol="BTC/USDT", timeframe="1d", source="binance"):
    cfg = {
        "strategy": {"template_id": f"user_{uid}"},
        "symbol": symbol, "market": "crypto", "timeframe": timeframe,
        "source": source, "initial_capital": 100000.0, "commission": 0.001,
        "engine": "bar",
    }
    r = requests.post(f"{API}/backtest/run", headers=H, json=cfg, timeout=30)
    print("run:", r.status_code, r.text[:200])
    return r.json().get("task_id") or r.json().get("id")

def poll(task_id, wait=40):
    for _ in range(wait):
        r = requests.get(f"{API}/backtest/{task_id}", headers=H, timeout=15)
        d = r.json()
        st = d.get("status") or d.get("state")
        if st in ("done", "completed", "success"):
            m = d.get("metrics") or d.get("result", {}).get("metrics", {})
            return m
        if st in ("error", "failed"):
            return {"error": d.get("error") or d.get("detail")}
        time.sleep(5)
    return {"error": "timeout polling"}

if __name__ == "__main__":
    py = sys.argv[1] if len(sys.argv) > 1 else "strategies/combo_KCxVolZ.py"
    uid = upload(py)
    print("uploaded id:", uid)
    if not uid:
        sys.exit(1)
    tid = run_backtest(uid)
    print("task:", tid)
    res = poll(tid)
    print("RESULT:", json.dumps(res, ensure_ascii=False)[:800])
