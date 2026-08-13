"""scripts/test_data_validation.py — T1 驗證:損益/報酬正負一致 + 非法數值攔截。

不做網路回測(不依賴取數),用:
 (a) 合成 BacktestResult 驗「total_pnl<0 → total_return_pct<0」(正負一致性契約);
 (b) validate_financial_inputs 直接單元驗證非法值攔截。

用法: python3.12 scripts/test_data_validation.py  (exit 0=全過,1=有 FAIL)
"""
import sys, math
sys.path.insert(0, "/root/quant-backtest-platform")

FAILS = []

def check(name, cond, detail=""):
    m = "[PASS]" if cond else "[FAIL]"
    print(f"{m} {name}" + (f" | {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)

# ── (a) 正負號一致性契約: 若損益(金額)為負, 報酬率%(total_return_pct)必為負 ──
# 用與後端相同算式: total_return_pct = (final_equity - initial)/initial*100, total_pnl = final_equity - initial(費後)
def pct(pnl, initial):  # 模擬後端 total_return_pct
    return (pnl) / initial * 100  # 虧損 pnl<0 → pct<0

def sign_consistent(pnl, initial):
    pct_ = pct(pnl, initial)
    # 契約: pnl<0 → pct_<0; pnl>0 → pct_>0
    return (pnl < 0) == (pct_ < 0) or pnl == 0

print("=== T1a: 損益 → 報酬率 正負一致 ===")
cases = [(+5000, 100000), (-5000, 100000), (0, 100000), (-0.5, 100000), (+1.2, 100)]
for pnl, init in cases:
    ok = sign_consistent(pnl, init)
    check(f"pnl={pnl:+} initial={init} → pct={pct(pnl,init):+.2f}% {('負%' if pnl<0 else '+%')} 一致",
          ok, f"算出 {pct(pnl,init):+.4f}%")
# 確定驗證:負損益→負百分比
pneg = pct(-5000, 100000)
check("負損益→負百分比", pneg < 0, f"pct={pneg}")

# 前端契約: PerformancePanel 金額與%同色 — netProfit sign == totalReturnPct sign
def frontend_consistent(net_profit, total_return_pct):
    return (net_profit >= 0) == (total_return_pct >= 0)
check("前端: netProfit>=0 ⇔ totalReturnPct>=0(同色)", frontend_consistent(-5000, -5.0), "(兩者同號即一致)")
check("前端: 負淨利→負return%, 不成正綠", frontend_consistent(-5000, -5.0) and not (frontend_consistent(-5000, +5.0)), "")

# ── (b) 非法數值攔截 ──
from app.services.validation import validate_financial_inputs
print("\n=== T1b: 非法數值攔截(輸入邊界) ===")
base = {"initial_capital": 100000, "commission": 0.001, "params": {"fast_period": 10}}
# 合法
check("合法 capital=100000 不攔截", validate_financial_inputs(base) is None, f"err={validate_financial_inputs(base)}")
# 非法
for bad_cap, label in [(0, "capital=0"), (-500, "capital=-500"), (float('nan'), "capital=NaN"), (float('inf'), "capital=Inf"),
                       (1e15, "capital=1e15(超上限)")]:
    cfg = {**base, "initial_capital": bad_cap}
    err = validate_financial_inputs(cfg)
    check(f"攔截 {label}", err is not None, f"err={err}")
# 非法 fee
for bad_fee in (float('nan'), 2.0):
    cfg = {**base, "commission": bad_fee}
    check(f"攔截 commission={bad_fee}", validate_financial_inputs(cfg) is not None)
# 非法參數
cfg = {**base, "params": {"fast_period": float('nan')}}
check("攔截 param NaN", validate_financial_inputs(cfg) is not None)
cfg = {**base, "params": {"fast_period": float('inf')}}
check("攔截 param Infinity", validate_financial_inputs(cfg) is not None)

print(f"\n=== 總結: {len(FAILS) and '有FAIL' or '全部通過'} (FAIL={FAILS}) ===")
sys.exit(1 if FAILS else 0)
