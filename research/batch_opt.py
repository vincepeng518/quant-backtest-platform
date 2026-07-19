"""batch_opt.py — 批量跑 optimize_local (NO_PUSH 由 env 控制)。
用法: python3 research/batch_opt.py <strategies_csv> <symbols_csv> <timeframes_csv>
例:   python3 research/batch_opt.py "breakout,moving_average" "BTC_USDT,ETH_USDT" "15m,30m,1h,4h,1d"
每個組合: research/optimize_local.py <strat_py> data/csv/<SYM>_<TF>.csv
已有的 opt_*.json 跳過 (不重複)。
"""
from __future__ import annotations
import os, sys, subprocess, glob
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRAT_DIR = os.path.join(PROJ, "strategies")
HIST = os.path.join(PROJ, "backtest_history")

def strat_py(name: str) -> str:
    # name like breakout -> strategies/technical/breakout.py
    cand = [
        os.path.join(STRAT_DIR, "technical", f"{name}.py"),
        os.path.join(STRAT_DIR, "combo", f"{name}.py"),
    ]
    for c in cand:
        if os.path.exists(c):
            return c
    return cand[0]

def main():
    strats = sys.argv[1].split(",") if len(sys.argv) > 1 else ["breakout"]
    syms = sys.argv[2].split(",") if len(sys.argv) > 2 else ["BTC_USDT"]
    tfs = sys.argv[3].split(",") if len(sys.argv) > 3 else ["1h"]
    done = 0; skip = 0; fail = 0
    for s in strats:
        py = strat_py(s)
        if not os.path.exists(py):
            print(f"NO STRAT {s}")
            continue
        base = os.path.splitext(os.path.basename(py))[0]
        for sym in syms:
            for tf in tfs:
                csv = os.path.join(PROJ, "data", "csv", f"{sym}_{tf}.csv")
                if not os.path.exists(csv):
                    continue
                # 跳過已有
                pat = os.path.join(HIST, f"opt_{base}_{sym}_{tf}_*.json")
                if glob.glob(pat):
                    skip += 1
                    continue
                cmd = [sys.executable, os.path.join(PROJ, "research", "optimize_local.py"), py, csv]
                r = subprocess.run(cmd, env={**os.environ, "NO_PUSH": "1"},
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=200)
                if r.returncode == 0:
                    done += 1
                else:
                    fail += 1
                    print(f"FAIL {base} {sym} {tf}")
    print(f"done={done} skip={skip} fail={fail}")

if __name__ == "__main__":
    main()
