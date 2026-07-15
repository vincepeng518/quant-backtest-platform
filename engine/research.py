# engine/research.py
from __future__ import annotations
from typing import Any, Optional

import numpy as np
import pandas as pd


def _log_returns(df: pd.DataFrame) -> pd.Series:
    close = df["close"].astype(float)
    return np.log(close / close.shift(1)).dropna()


def _hurst(returns: pd.Series) -> float:
    # R/S rescaled range via aggregated lagged std
    lags = range(2, min(20, len(returns) // 4))
    if len(returns) < 20 or not list(lags):
        return 0.5
    tau: list[float] = []
    lag_vals: list[int] = []
    for lag in lags:
        chunks = len(returns) // lag
        if chunks == 0:
            continue
        rs = []
        for i in range(chunks):
            sub = returns[i * lag:(i + 1) * lag]
            if len(sub) < 2:
                continue
            mean = sub.mean()
            dev = sub - mean
            z = np.cumsum(dev)
            r = float(np.max(z) - np.min(z))
            s = float(sub.std(ddof=1))
            if s > 0:
                rs.append(r / s)
        if rs:
            tau.append(float(np.mean(rs)))
            lag_vals.append(lag)
    if len(tau) < 2:
        return 0.5
    poly = np.polyfit(np.log(lag_vals), np.log(tau), 1)
    return float(np.clip(poly[0], 0.01, 0.99))


def market_profile(df: pd.DataFrame, benchmark: Optional[pd.DataFrame] = None) -> dict[str, Any]:
    ret = _log_returns(df)
    if len(ret) < 5:
        return {
            "returns_stats": {}, "autocorrelation": {}, "hurst": 0.5,
            "vol_regime": {"windows": []}, "correlation": None, "seasonality": {},
        }
    returns_stats = {
        "mean": float(ret.mean()),
        "std": float(ret.std()),
        "skew": float(ret.skew()),
        "kurtosis": float(ret.kurtosis()),
        "annualized_vol": float(ret.std() * np.sqrt(252)),
    }
    autocorr = {f"lag_{l}": float(ret.autocorr(l)) for l in (1, 2, 3, 5, 10) if l < len(ret)}
    hurst = _hurst(ret)
    # rolling vol regime: 30-bar std, flag top/bottom 20% quantiles as high/low
    roll = ret.rolling(30).std()
    q_hi = float(roll.quantile(0.8))
    q_lo = float(roll.quantile(0.2))
    windows = []
    for i, v in enumerate(roll.dropna().values):
        regime = "high" if v >= q_hi else ("low" if v <= q_lo else "normal")
        windows.append({"i": int(i), "vol": float(v), "regime": regime})
    corr = None
    if benchmark is not None and len(benchmark) == len(df):
        bret = _log_returns(benchmark)
        if len(bret) == len(ret):
            corr = float(pd.concat([ret, bret], axis=1).dropna().corr().iloc[0, 1])
    seasonality = {
        int(d): float(mean_val)
        for d, mean_val in ret.to_frame("ret").assign(
            dow=pd.to_datetime(df["timestamp"]).dt.dayofweek[ret.index]
        ).groupby("dow")["ret"].mean().items()
    }
    return {
        "returns_stats": returns_stats,
        "autocorrelation": autocorr,
        "hurst": hurst,
        "vol_regime": {"windows": windows, "q_high": q_hi, "q_low": q_lo},
        "correlation": corr,
        "seasonality": seasonality,
    }


from strategies.base import StrategyBase, Bar


def _row_to_bar(row) -> Bar:
    return Bar(
        timestamp=row["timestamp"],
        open=float(row["open"]), high=float(row["high"]),
        low=float(row["low"]), close=float(row["close"]),
        volume=float(row["volume"]),
    )


def signal_profile(df: pd.DataFrame, strategy_cls: type[StrategyBase], params: dict) -> dict[str, Any]:
    strat = strategy_cls()
    strat.init(params)
    signals: list[str] = []
    entry_prices: list[float] = []
    fwd_rets: list[float] = []
    closes = df["close"].astype(float).values
    for i, (_, row) in enumerate(df.iterrows()):
        sig = strat.next(_row_to_bar(row))
        if sig is None:
            continue
        if sig.action in ("buy", "sell", "close_buy", "close_sell"):
            signals.append(sig.action)
            entry_prices.append(float(row["close"]))
            # forward return N=5 bars
            if i + 5 < len(closes):
                fwd_rets.append(float(np.log(closes[i + 5] / closes[i])))
    counts: dict[str, int] = {}
    for s in signals:
        counts[s] = counts.get(s, 0) + 1
    longs = sum(v for k, v in counts.items() if "buy" in k)
    shorts = sum(v for k, v in counts.items() if "sell" in k)
    total = longs + shorts
    lsm = (longs / total) if total else 0.0
    # entry timing: price percentile within rolling 50-bar window
    timing = []
    roll = df["close"].rolling(50)
    for p in entry_prices:
        lo, hi = roll.min().iloc[-1], roll.max().iloc[-1]
        timing.append(float((p - lo) / (hi - lo)) if hi > lo else 0.5)
    return {
        "signal_counts": counts,
        "long_short_ratio": lsm,
        "entry_timing": {"mean_percentile": float(np.mean(timing)) if timing else 0.5,
                          "samples": len(timing)},
        "signal_forward_return": {"mean": float(np.mean(fwd_rets)) if fwd_rets else 0.0,
                                   "n": len(fwd_rets)},
    }
