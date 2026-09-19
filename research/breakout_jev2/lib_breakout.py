"""突破策略通用回測核心 —— 支援多種出場方法與多時間級別。

設計理由（來自前幾輪的失敗教訓）：
  前幾輪只測試了「固定 ATR 停損/停利 OCO」一種出場。這是趨勢跟隨系統的結構性錯誤——
  固定停利會把大趨勢砍在半路，而趨勢跟隨的獲利本來就來自少數極端獲利單。
  本模組把出場方法參數化，這是前幾輪完全沒測過的一維。

出場方法：
  oco        固定 ATR 停損/停利（對照組，已知失敗）
  trail      吊燈式移動停損：stop = 進場後最高價 - k*ATR
  donchian   唐奇安出場：收盤跌破前 M 根最低（經典海龜出場）
  time       固定持倉 N 根後出場

資料介面：DataFrame 需有 timestamp/open/high/low/close/volume 與 don_hi_<L>/don_lo_<L>。
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

FEE_TAKER = 0.0005
SLIPPAGE = 0.0002


def prepare(df: pd.DataFrame, lookbacks: list[int], exit_lookbacks: list[int]) -> pd.DataFrame:
    """加上 ATR 與各 lookback 的 Donchian 通道（全部 shift(1)，無未來函數）。"""
    out = df.copy()
    hi, lo, cl = out["high"], out["low"], out["close"]
    tr = pd.concat([hi - lo, (hi - cl.shift()).abs(), (lo - cl.shift()).abs()], axis=1).max(axis=1)
    out["atr"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    for lb in set(lookbacks) | set(exit_lookbacks):
        out[f"don_hi_{lb}"] = out["high"].rolling(lb).max().shift(1)
        out[f"don_lo_{lb}"] = out["low"].rolling(lb).min().shift(1)
    return out


def backtest_breakout(
    df: pd.DataFrame,
    *,
    lookback: int = 96,
    direction: str = "both",       # long | short | both
    exit_method: str = "trail",    # oco | trail | donchian | time
    stop_atr: float = 2.0,
    target_atr: float = 4.0,
    trail_atr: float = 3.0,
    exit_lookback: int = 48,
    max_hold: int = 200,
    fee: float = FEE_TAKER,
    slippage: float = SLIPPAGE,
    start: int = 0,
    end: Optional[int] = None,
    brk_max_atr: Optional[float] = None,
) -> tuple[list[dict[str, Any]], np.ndarray]:
    """跑一次突破回測。

    進場：第 i 根收盤突破 → 第 i+1 根**開盤**進場（無未來函數）。
    回傳 (trades, equity_curve)。含手續費與滑價。
    """
    n = len(df) if end is None else int(end)
    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    a = df["atr"].values
    dhi = df[f"don_hi_{lookback}"].values
    dlo = df[f"don_lo_{lookback}"].values
    xlo = df[f"don_lo_{exit_lookback}"].values if exit_method == "donchian" else None
    xhi = df[f"don_hi_{exit_lookback}"].values if exit_method == "donchian" else None
    ts = df["timestamp"].values

    eq = 1.0
    eqs: list[float] = []
    trades: list[dict[str, Any]] = []
    busy_until = -1

    for i in range(start, n - 1):
        if i <= busy_until or np.isnan(a[i]) or a[i] <= 0 or np.isnan(dhi[i]):
            eqs.append(eq)
            continue

        sig = 0
        if direction in ("long", "both") and c[i] > dhi[i]:
            brk = (c[i] - dhi[i]) / a[i]
            if brk_max_atr is None or brk <= brk_max_atr:
                sig = 1
        if sig == 0 and direction in ("short", "both") and c[i] < dlo[i]:
            brk = (dlo[i] - c[i]) / a[i]
            if brk_max_atr is None or brk <= brk_max_atr:
                sig = -1
        if sig == 0:
            eqs.append(eq)
            continue

        e = i + 1
        entry = o[e]
        if entry <= 0:
            eqs.append(eq)
            continue

        d = sig
        a_tr = a[i]
        stop = entry - d * stop_atr * a_tr
        trail_ref = entry
        ex: Optional[float] = None
        ei: Optional[int] = None
        reason = ""

        for j in range(e, min(e + max_hold, n)):
            # 移動停損：先更新參考高/低（不含當根，避免同根先動後觸）
            if exit_method == "trail":
                stop = max(stop, trail_ref - trail_atr * a_tr) if d > 0 else \
                       min(stop, trail_ref + trail_atr * a_tr)
            if d > 0:
                if l[j] <= stop:
                    ex, ei, reason = stop, j, exit_method
                    break
                if exit_method == "oco" and h[j] >= entry + target_atr * a_tr:
                    ex, ei, reason = entry + target_atr * a_tr, j, "oco_tp"
                    break
                if exit_method == "donchian" and not np.isnan(xlo[j]) and c[j] < xlo[j]:
                    ex, ei, reason = c[j], j, "donchian"
                    break
                trail_ref = max(trail_ref, h[j])
            else:
                if h[j] >= stop:
                    ex, ei, reason = stop, j, exit_method
                    break
                if exit_method == "oco" and l[j] <= entry - target_atr * a_tr:
                    ex, ei, reason = entry - target_atr * a_tr, j, "oco_tp"
                    break
                if exit_method == "donchian" and not np.isnan(xhi[j]) and c[j] > xhi[j]:
                    ex, ei, reason = c[j], j, "donchian"
                    break
                trail_ref = min(trail_ref, l[j])

        if ex is None:
            ei = min(e + max_hold - 1, n - 1)
            ex = c[ei]
            reason = "max_hold"

        gross = d * (ex - entry) / entry - slippage * 2
        ret = gross - 2 * fee
        eq *= (1.0 + ret)
        trades.append({
            "i": e, "dir": d, "ret": float(ret), "bars": int(ei - e), "reason": reason,
            "entry": float(entry), "exit": float(ex),
            "ts_entry": str(pd.Timestamp(ts[e])), "ts_exit": str(pd.Timestamp(ts[ei])),
        })
        busy_until = ei
        for _ in range(ei - i):
            eqs.append(eq)
        if eq <= 0:
            break

    while len(eqs) < n:
        eqs.append(eq)
    return trades, np.array(eqs[:n], dtype=float)


def metrics(trades: list[dict[str, Any]], eqs: np.ndarray, bars: int,
            bars_per_year: float) -> dict[str, Any]:
    if not trades:
        return {"n": 0, "sharpe": 0.0, "wr": 0.0, "pf": 0.0, "maxdd_pct": 0.0,
                "ret_pct": 0.0, "avg_pct": 0.0, "expectancy": 0.0,
                "payoff": 0.0, "avg_bars": 0.0, "trades_per_year": 0.0,
                "max_win_pct": 0.0, "max_loss_pct": 0.0}
    r = np.array([t["ret"] for t in trades], dtype=float)
    eq = eqs if len(eqs) else np.array([1.0])
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / np.where(peak == 0, 1, peak)
    wins = r[r > 0]
    losses = r[r < 0]
    pf = float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else 999.0
    payoff = float(wins.mean() / abs(losses.mean())) if len(wins) and len(losses) else (
        999.0 if len(wins) else 0.0)     # 無虧損時用 999 sentinel（與 PF 慣例一致）
    sd = r.std(ddof=1) if len(r) > 1 else 0.0
    years = max(bars / bars_per_year, 1e-9)
    tpy = len(r) / years
    sharpe = float(r.mean() / sd * np.sqrt(tpy)) if sd > 0 else 0.0
    return {
        "n": len(trades), "sharpe": sharpe, "wr": float(len(wins) / len(r)),
        "pf": pf, "payoff": payoff, "maxdd_pct": float(dd.min() * 100),
        "ret_pct": float((eq[-1] - 1) * 100), "avg_pct": float(r.mean() * 100),
        "expectancy": float(r.mean()), "avg_bars": float(np.mean([t["bars"] for t in trades])),
        "trades_per_year": float(tpy), "years": float(years),
        "max_win_pct": float(r.max() * 100), "max_loss_pct": float(r.min() * 100),
    }
