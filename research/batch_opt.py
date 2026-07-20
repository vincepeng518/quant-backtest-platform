"""batch_opt.py — 批量跑 optimize_local (NO_PUSH 由 env 控制)。
用法: python3 research/batch_opt.py <strategies_csv> <symbols_csv> <timeframes_csv>
例:   python3 research/batch_opt.py "breakout,moving_average" "BTC_USDT,ETH_USDT" "15m,30m,1h,4h,1d"
每個組合: research/optimize_local.py <strat_py> data/csv/<SYM>_<TF>.csv
已有的 opt_*.json 跳過 (不重複)。
並行: 預設 PAR (env, 預設 min(cpu,3)) 個 worker 同時跑，縮短總時程。
"""
from __future__ import annotations
import os, sys, subprocess, glob, time
from subprocess import TimeoutExpired
from multiprocessing import Pool, cpu_count
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRAT_DIR = os.path.join(PROJ, "strategies")
HIST = os.path.join(PROJ, "backtest_history")
# 單組 timeout: 單組含 WF+MC1000 實測 ~212s，給足 900s 避免被誤殺
PER_TIMEOUT = int(os.environ.get("PER_TIMEOUT", "900"))
_NW = int(os.environ.get("PAR", "3"))
N_WORKERS = max(1, min(_NW, cpu_count()))


def strat_py(name: str) -> str:
    # 搜尋順序: technical/ -> strategies/ 根 -> combo_ 前綴 -> user/
    cand = [
        os.path.join(STRAT_DIR, "technical", f"{name}.py"),
        os.path.join(STRAT_DIR, f"{name}.py"),
        os.path.join(STRAT_DIR, f"combo_{name}.py"),
        os.path.join(STRAT_DIR, "user", f"{name}.py"),
    ]
    for c in cand:
        if os.path.exists(c):
            return c
    return cand[0]


def build_jobs(strats, syms, tfs, FORCE):
    jobs = []
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
                pat = os.path.join(HIST, f"opt_{base}_{sym}_{tf}_*.json")
                existing = glob.glob(pat)
                if existing:
                    if FORCE:
                        for f in existing:
                            os.remove(f)
                        jobs.append(("run", base, sym, tf, py, csv))
                    else:
                        jobs.append(("skip", base, sym, tf, py, csv))
                else:
                    jobs.append(("run", base, sym, tf, py, csv))
    return jobs


def worker(job):
    kind, base, sym, tf, py, csv = job
    if kind == "skip":
        return (base, sym, tf, "skip", "")
    cmd = [sys.executable, os.path.join(PROJ, "research", "optimize_local.py"), py, csv]
    try:
        r = subprocess.run(cmd, env={**os.environ, "NO_PUSH": "1"},
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=PER_TIMEOUT)
        if r.returncode == 0:
            return (base, sym, tf, "done", "")
        return (base, sym, tf, "fail", f"rc={r.returncode}")
    except subprocess.TimeoutExpired:
        return (base, sym, tf, "fail", f"timeout>{PER_TIMEOUT}s")
    except Exception as e:  # noqa
        return (base, sym, tf, "fail", str(e)[:120])


def main():
    strats = sys.argv[1].split(",") if len(sys.argv) > 1 else ["breakout"]
    syms = sys.argv[2].split(",") if len(sys.argv) > 2 else ["BTC_USDT"]
    tfs = sys.argv[3].split(",") if len(sys.argv) > 3 else ["1h"]
    FORCE = os.environ.get("FORCE") == "1"
    jobs = build_jobs(strats, syms, tfs, FORCE)
    run_jobs = [j for j in jobs if j[0] == "run"]
    skip = sum(1 for j in jobs if j[0] == "skip")
    done = 0
    fail = 0
    fails = []
    t0 = time.time()
    print(f"workers={N_WORKERS} total={len(jobs)} run={len(run_jobs)} skip={skip} FORCE={FORCE}")
    with Pool(N_WORKERS) as pool:
        for i, res in enumerate(pool.imap_unordered(worker, run_jobs), 1):
            base, sym, tf, status, msg = res
            if status == "done":
                done += 1
            else:
                fail += 1
                fails.append(f"{base} {sym} {tf} ({msg})")
                print(f"FAIL {base} {sym} {tf} {msg}")
            if i % 10 == 0 or i == len(run_jobs):
                el = time.time() - t0
                print(f"progress {i}/{len(run_jobs)} done={done} fail={fail} skip={skip} elapsed={el:.0f}s")
    print(f"done={done} skip={skip} fail={fail}")
    if fails:
        print("FAILLIST:")
        for f in fails:
            print("  " + f)


if __name__ == "__main__":
    main()
