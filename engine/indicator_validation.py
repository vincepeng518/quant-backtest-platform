from __future__ import annotations

"""Indicator validation pipeline (borrowed concept from TradingView-API's use case).

We compute indicators in Python (the same way the backtest engine does) and
let the user supply *reference* values (e.g. from TradingView's chart, a
different library, or a known-good dataset). The pipeline reports per-bar
delta + max abs error so we can catch divergence bugs in our indicator code.

NOTE: we do NOT call TradingView's private WebSocket (ToS violation / unstable).
The reference values are supplied by the caller; this module only compares.
"""

import numpy as np
import pandas as pd
from typing import Any, Optional


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-12)
    return 100 - (100 / (1 + rs))


_INDICATORS = {
    "sma": lambda s, p: sma(s, p),
    "ema": lambda s, p: ema(s, p),
    "rsi": lambda s, p: rsi(s, p),
}


def compute_indicator(close: pd.Series, name: str, period: int) -> pd.Series:
    if name not in _INDICATORS:
        raise ValueError(f"unknown indicator {name}; supported: {list(_INDICATORS)}")
    return _INDICATORS[name](close, period)


def validate(
    close: pd.Series,
    name: str,
    period: int,
    reference: pd.Series,
    tol: float = 1e-6,
) -> dict:
    """Compare our computed indicator against a reference series.

    Returns: {name, period, n, max_abs_error, mean_abs_error, matched, mismatches}
    """
    ours = compute_indicator(close, name, period)
    # align on index
    df = pd.DataFrame({"ours": ours, "ref": reference}).dropna()
    diff = (df["ours"] - df["ref"]).abs()
    matched = bool((diff <= tol).all())
    mismatches = int((diff > tol).sum())
    return {
        "name": name,
        "period": period,
        "n": int(len(df)),
        "max_abs_error": float(diff.max()) if len(diff) else 0.0,
        "mean_abs_error": float(diff.mean()) if len(diff) else 0.0,
        "matched": matched,
        "mismatches": mismatches,
    }
