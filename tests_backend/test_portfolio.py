"""engine/portfolio 單元驗證: 相關性矩陣準確度 + 組合計算 + 異常負值防護。"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.portfolio import run_portfolio, correlation_matrix, compute_returns

ok = True
def check(name, cond, detail=""):
    global ok
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")
    if not cond: ok = False

# ── T1: 相關性矩陣準確度(已知相關係數)──
random.seed(1)
n = 200
x = [random.gauss(0,1) for _ in range(n)]
y = [0.9*xi + 0.1*random.gauss(0,1) for xi in x]   # corr≈0.9+
z = [-xi + 0.1*random.gauss(0,1) for xi in x]      # corr≈-1
# 轉成 equity(1+return 累乘)
def to_eq(returns):
    eq=[100.0]
    for r in returns: eq.append(eq[-1]*(1+r))
    return eq
EX, EY, EZ = to_eq(x), to_eq(y), to_eq(z)
m = correlation_matrix({"X":x,"Y":y,"Z":z})
print("corr X-Y:", m["X"]["Y"], " X-Z:", m["X"]["Z"], " 對角:", m["X"]["X"])
check("X,Y 正相關(>0.5)", m["X"]["Y"]>0.5, f"得{m['X']['Y']}")
check("X,Z 負相關(<-0.5)", m["X"]["Z"]<-0.5, f"得{m['X']['Z']}")
check("對角線=1", abs(m["X"]["X"]-1)<1e-6)

# ── T2: 回報空間等權組合正確性(用健康回報, 不觸發爆倉clip)──
random.seed(2)
hx = [0.001*random.gauss(0,1) for _ in range(150)]      # 小波動, 永不在 -1 以下
hy = [0.001*random.gauss(0,1) for _ in range(150)]
EH = to_eq(hx); EH2 = to_eq(hy)
pf = run_portfolio({"X":EH,"Y":EH2}, weights={"X":0.5,"Y":0.5})
exp_rets = [0.5*rx+0.5*ry for rx,ry in zip(hx,hy)]
exp_eq=[100.0]
for r in exp_rets: exp_eq.append(exp_eq[-1]*(1+r))
check("回報空間等權組合 equity 正確", len(pf.portfolio_equity)==len(exp_eq) and all(abs(a-b)<1e-6 for a,b in zip(pf.portfolio_equity,exp_eq)), f"長度{len(pf.portfolio_equity)}")
check("健康eq無clip警告", not any("≤0 equity" in e for e in pf.errors), f"errors={pf.errors}")
check("相關性矩陣有2標的", set(pf.correlation_matrix.keys())=={"X","Y"})

# ── T3: 異常負值防護 ──
# 3a. 爆倉防護: 單標equity跌破0 → 爆倉退出組合並記錄
pf_zero = run_portfolio({"X":[100,50,30,-10,5], "Y":[100,110,120,130,140]})
check("負equity爆倉被記錄", any("爆倉" in e for e in pf_zero.errors), f"errors={pf_zero.errors}")
# 3b. 負權重對沖被記錄(健康eq)
random.seed(3)
wx=[0.002*random.gauss(0,1) for _ in range(120)]; wy=[0.002*random.gauss(0,1) for _ in range(120)]
EWx, EWy = to_eq(wx), to_eq(wy)
pf_bad = run_portfolio({"X":EWx,"Y":EWy}, weights={"X":-0.5,"Y":1.5})
check("負權重被記錄", any("負值" in e for e in pf_bad.errors), f"errors={pf_bad.errors}")
# 3c. 非有限值 equity
pf_nan = run_portfolio({"X":[100,float('nan'),120], "Y":[100,110,125]})
check("NaN equity 卡關回報", len(pf_nan.errors)>0, f"errors={pf_nan.errors}")

# ── T4: 負相關標的「同做多」天然對沖 → 降組合波動 ──
# X 與 Z 負相關(≈-0.99, 即 Z≈-X): 兩者同做多 → 組合回報互相抵消 → 波動應大幅 < 各自
# (負相關資產本身反向, 同向持倉即自然對沖; 這才是「組合對沖」的數學)
pf_hedge = run_portfolio({"X":EX,"Z":EZ}, weights={"X":1.0,"Z":1.0})
pv = pf_hedge.portfolio_metrics["volatility_annual"]
xv = pf_hedge.individual_metrics["X"]["volatility_annual"]
zv = pf_hedge.individual_metrics["Z"]["volatility_annual"]
print(f"同做多負相關組合vol={pv} vs X={xv} vs Z={zv}")
check("負相關同做多組合vol < 單標", pv is not None and xv is not None and pv < min(xv, zv),
       f"組合{pv} < min({xv},{zv})")
check("hedge_report 抓到負相關對", any(p["corr"]<0 for p in pf_hedge.hedge_report["negative_corr_pairs"]))

# ── T5: 時間對齊(不同長度, 交集)──
pf_t = run_portfolio(
    {"X":[100,101,102,103], "Y":[100,105,110,115]},
    timestamps_by_symbol={"X":[1,2,3,4], "Y":[2,3,4]},
)
# 交集 ts=[2,3,4] → 各取 index 1,2,3
check("時間對齊交集", pf_t.timestamps==[2,3,4], f"tss={pf_t.timestamps}")
check("對齊後組合長度=3", len(pf_t.portfolio_equity)==3)

print("\n=== 總結:", "全部通過" if ok else "有FAIL ===")
sys.exit(0 if ok else 1)
