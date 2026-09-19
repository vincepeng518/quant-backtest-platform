"""5m 突破純量回測核心。

與 research/breakout_jev/ 舊版差異：
  1. 回傳 per-trade 報酬，讓槓桿可事後線性套用（回測內亦支援 leverage 參數）；
  2. 支援爆倉判定（維持保證金）與資金費率扣款；
  3. 支援參數網格平行化（ProcessPoolExecutor）。
"""
from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd


def load_env(path: str = "/root/Crypto-Backtesting-Lab/.env.local") -> None:
    """把 .env.local 的 KEY=VALUE 讀進 os.environ（不覆蓋既有值）。

    為什麼需要：`AI_GATEWAY_API_KEY` 只存在 .env.local（該檔被 .gitignore 忽略），
    shell 不會自動載入。任何需要 Jev 的腳本（只有 s4）必須先呼叫這個。
    """
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


BARS_PER_YEAR_5M = 105_120
MAINT_MARGIN = 0.005          # 維持保證金 0.5%（簡化：不分級距）
FEE_TAKER = 0.0005
SLIPPAGE = 0.0002
MAX_HOLD = 288                # 24 小時


def backtest(
    df: pd.DataFrame,
    lookback: int,
    stop_atr: float,
    target_atr: float,
    brk_max: float,
    *,
    fee: float = FEE_TAKER,
    slippage: float = SLIPPAGE,
    leverage: float = 1.0,
    long_only: bool = True,
    funding_per_8h: float = 0.0,
    start: int = 0,
    end: Optional[int] = None,
    jev_gate: Optional[np.ndarray] = None,
) -> tuple[list[dict[str, Any]], np.ndarray]:
    """跑一次回測。

    jev_gate: 可選，長度 = len(df) 的 0/1 陣列；0 表示該棒訊號被 Jev 否決。
    回傳 (trades, equity_curve)。trades[i]['ret'] 為**槓桿後**權益報酬。
    """
    n = len(df) if end is None else int(end)
    o = df["open"].values; h = df["high"].values
    l = df["low"].values;  c = df["close"].values
    atr = df["atr"].values
    dhi = df["don_hi"].values; dlo = df["don_lo"].values
    ts = df["timestamp"].values

    eq = 1.0
    eqs: list[float] = []
    trades: list[dict[str, Any]] = []
    busy_until = -1

    for i in range(start, n - 1):
        if i <= busy_until or np.isnan(atr[i]) or np.isnan(dhi[i]):
            eqs.append(eq); continue
        a = atr[i]
        if a <= 0:
            eqs.append(eq); continue

        sigs: list[int] = []
        if c[i] > dhi[i] and (c[i] - dhi[i]) / a <= brk_max:
            sigs.append(1)
        if not long_only and c[i] < dlo[i] and (dlo[i] - c[i]) / a <= brk_max:
            sigs.append(-1)
        if not sigs:
            eqs.append(eq); continue
        d = sigs[0]
        if jev_gate is not None and jev_gate[i] == 0:
            eqs.append(eq); continue

        e = i + 1
        entry = o[e]
        if entry <= 0:
            eqs.append(eq); continue

        stop = entry - d * stop_atr * a
        tgt = entry + d * target_atr * a
        liq_px = entry * (1 - d * (1.0 / leverage - MAINT_MARGIN)) if leverage > 1 else None

        ex: Optional[float] = None
        ei: Optional[int] = None
        liq = False
        for j in range(e, min(e + MAX_HOLD, n)):
            if liq_px is not None:
                hit_liq = (l[j] <= liq_px) if d > 0 else (h[j] >= liq_px)
                if hit_liq:
                    ex, ei, liq = liq_px, j, True
                    break
            if d > 0:
                if l[j] <= stop: ex, ei = stop, j; break
                if h[j] >= tgt:  ex, ei = tgt, j; break
            else:
                if h[j] >= stop: ex, ei = stop, j; break
                if l[j] <= tgt:  ex, ei = tgt, j; break
        if ex is None:
            ei = min(e + MAX_HOLD - 1, n - 1)
            ex = c[ei]

        bars = ei - e
        if liq:
            ret = -1.0
        else:
            gross = d * (ex - entry) / entry
            gross -= slippage * 2                      # 進出各一次滑價
            ret = leverage * gross - 2 * fee * leverage
            funding = funding_per_8h * (bars / 96.0)   # 96 根 5m = 8h
            ret -= leverage * funding

        eq *= (1.0 + ret)
        if eq < 1e-9:
            eq = 0.0
        trades.append({
            "i": e, "dir": d, "ret": float(ret), "bars": int(bars), "liq": liq,
            "entry": float(entry), "exit": float(ex),
            "ts_entry": str(pd.Timestamp(ts[e])), "ts_exit": str(pd.Timestamp(ts[ei])),
        })
        busy_until = ei
        for _ in range(ei - i):
            eqs.append(eq)
        if eq <= 0.0:
            while len(eqs) < n:
                eqs.append(0.0)
            break

    while len(eqs) < n:
        eqs.append(eq)
    return trades, np.array(eqs[:n], dtype=float)


def metrics(trades: list[dict[str, Any]], eqs: np.ndarray, bars: int) -> dict[str, Any]:
    """Sharpe 以**每筆交易**為單位後年化；報酬以權益曲線為準。"""
    if not trades:
        return {"n": 0, "sharpe": 0.0, "wr": 0.0, "pf": 0.0, "maxdd_pct": 0.0,
                "ret_pct": 0.0, "avg_pct": 0.0, "avg_bars": 0.0,
                "trades_per_day": 0.0, "months": bars / (12 * 24 * 12)}
    r = np.array([t["ret"] for t in trades], dtype=float)
    eq = eqs if len(eqs) else np.array([1.0])
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / np.where(peak == 0, 1, peak)
    wins = r[r > 0]; losses = r[r < 0]
    pf = float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else 999.0
    sd = r.std(ddof=1) if len(r) > 1 else 0.0
    years = max(bars / BARS_PER_YEAR_5M, 1e-9)
    tpy = len(r) / years
    sharpe = float(r.mean() / sd * np.sqrt(tpy)) if sd > 0 else 0.0
    return {
        "n": len(trades), "sharpe": sharpe,
        "wr": float(len(wins) / len(r)),
        "pf": pf,
        "maxdd_pct": float(dd.min() * 100),
        "ret_pct": float((eq[-1] - 1) * 100),
        "avg_pct": float(r.mean() * 100),
        "avg_bars": float(np.mean([t["bars"] for t in trades])),
        "trades_per_day": float(len(r) / (bars / 288.0)),
        "months": float(bars / (12 * 24 * 12)),
    }


def monthly_series(eqs: np.ndarray, bars_per_month: int = 12 * 24 * 12) -> list[float]:
    """把權益曲線切成月報酬（%）。"""
    out = []
    for k in range(1, len(eqs) // bars_per_month + 1):
        a = eqs[(k - 1) * bars_per_month]
        b = eqs[k * bars_per_month]
        if a > 0:
            out.append((b / a - 1) * 100)
    return out


def _worker(args):
    df, grid_row, kwargs = args
    tr, eq = backtest(df, *grid_row, **kwargs)
    m = metrics(tr, eq, len(df))
    m["params"] = list(grid_row)
    return m


def run_grid(df, grid: Iterable[tuple], *, workers: int = 3, **kwargs) -> list[dict]:
    """平行跑參數網格，回傳按 Sharpe 由高到低排序的 metrics 清單。"""
    jobs = [(df, row, kwargs) for row in grid]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(_worker, jobs))
    return sorted(res, key=lambda m: m["sharpe"], reverse=True)
