from __future__ import annotations

import numpy as np
import pandas as pd

from strategies.base import Bar, Signal, StrategyBase


def momentum(close: pd.Series, window: int = 20) -> float:
    """Return over trailing `window` bars (normalized)."""
    if len(close) < window + 1:
        return 0.0
    return float((close.iloc[-1] / close.iloc[-1 - window] - 1.0) * 100.0)


def mean_reversion_zscore(close: pd.Series, window: int = 20) -> float:
    """Z-score of price vs rolling mean. Positive => overbought (short bias)."""
    if len(close) < window:
        return 0.0
    roll = close.iloc[-window:]
    mu = roll.mean()
    sd = roll.std()
    if sd == 0 or np.isnan(sd):
        return 0.0
    return float((close.iloc[-1] - mu) / sd)


def realized_vol(close: pd.Series, window: int = 20) -> float:
    """Annualized-ish realized vol (stdev of returns * sqrt(window))."""
    if len(close) < window + 1:
        return 0.0
    rets = close.iloc[-window - 1:].pct_change().dropna()
    if len(rets) == 0:
        return 0.0
    return float(rets.std() * np.sqrt(window) * 100.0)


def rsi(close: pd.Series, period: int = 14) -> float:
    """Wilder RSI (0-100). >70 overbought, <30 oversold."""
    if len(close) < period + 1:
        return 50.0
    delta = close.diff().dropna()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)
    ag = gains.rolling(period).mean().iloc[-1]
    al = losses.rolling(period).mean().iloc[-1]
    if al == 0:
        return 100.0
    rs = ag / al
    return float(100.0 - 100.0 / (1.0 + rs))


def roc(close: pd.Series, window: int = 10) -> float:
    """Rate of change % over `window` bars."""
    if len(close) < window + 1:
        return 0.0
    return float((close.iloc[-1] / close.iloc[-1 - window] - 1.0) * 100.0)


# Registry of available factors. Each maps to a compute fn(close, **kw) -> float.
FACTOR_REGISTRY = {
    "momentum": momentum,
    "mean_reversion": mean_reversion_zscore,
    "volatility": realized_vol,
    "rsi": rsi,
    "roc": roc,
}


def compute_factor(name: str, close: pd.Series, **kw) -> float:
    fn = FACTOR_REGISTRY.get(name)
    if fn is None:
        return 0.0
    # rsi uses `period` not `window`; normalize caller's window kwarg
    if name == "rsi":
        kw = {"period": kw.get("window", kw.get("period", 14))}
    return fn(close, **kw)
