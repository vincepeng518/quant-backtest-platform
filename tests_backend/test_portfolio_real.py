"""portfolio 真實數據整合測試: BTC/ETH/SOL 跑 ma_cross → 組合 + 相關性矩陣。
驗證真實市場數據下組合計算正確、相關性合理、無異常負值。
用法: python3.12 tests_backend/test_portfolio_real.py
"""
import asyncio, sys, os
sys.path.insert(0, '/root/quant-backtest-platform')

# 載入需求 env(若 DataService 需要)
for envf in ['/root/.env', '/root/.hermes/.env']:
    if os.path.exists(envf):
        for line in open(envf):
            line=line.strip()
            if line and not line.startswith('#') and '=' in line:
                k,v=line.split('=',1)
                os.environ.setdefault(k.strip(), v.strip())

from app.services.portfolio_service import run_portfolio_backtest

async def main():
    cfg = {
        "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        "strategy": {"template_id": "ma_cross", "params": {"fast_period": 10, "slow_period": 30}},
        "timeframe": "1d", "start_date": "2025-01-01", "end_date": "2025-06-01",
        "initial_capital": 100000, "commission": 0.0004, "source": "bingx",
    }
    try:
        res = await run_portfolio_backtest(cfg)
    except Exception as e:
        import traceback; traceback.print_exc()
        print("執行失敗:", e); return

    print("status:", res.get("status"))
    if res.get("status") == "error":
        print("錯誤:", res.get("error"))
        print("partial:", res.get("partial"))
        print("warnings:", res.get("warnings"))
        return
    print("=== 相關性矩陣(BTC/ETH/SOL) ===")
    cm = res["correlation_matrix"]
    for a in res["symbols"]:
        print(" ", a, {b: cm[a][b] for b in res["symbols"]})
    print("=== 組合風險 ===", res["portfolio_metrics"])
    print("=== 對沖報告 ===", res["hedge_report"])
    print("=== 各標的風險 ===")
    for s, m in res["pf_individual_metrics"].items():
        print(" ", s, m)
    # 異常負值防護檢查
    eq = res.get("portfolio_equity") or []
    import math
    bad = [i for i,v in enumerate(eq) if not math.isfinite(v)] if eq else []
    print("portfolio_equity 長度:", len(eq), "非有限:", bad[:5] if bad else "無")
    print("warnings:", res.get("warnings"))

asyncio.run(main())
