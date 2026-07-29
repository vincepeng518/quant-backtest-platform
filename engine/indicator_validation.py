from __future__ import annotations

"""
Indicator validation pipeline — using pandas_ta (TradingView-aligned).

pandas_ta uses the same EMA/RMA conventions as TradingView (RMA = Wilder's
smoothing = EMA(alpha=1/period, adjust=False)), so RSI, MACD, ATR, etc.
match the Pine Script reference calculations.

Usage:
    from engine.indicator_validation import compute, validate

    close = df["close"]
    rsi_series = compute(close, "rsi", 14)
    report = validate(close, "rsi", 14, reference_series)
"""

from typing import Any, Optional

import numpy as np
import pandas as pd

# Import pandas_ta lazily so the module loads without it
_TA: Any = None


def _ensure_ta():
    global _TA
    if _TA is None:
        try:
            import pandas_ta as _TA
        except ImportError:
            raise ImportError(
                "pandas_ta is required for vectorized indicators. "
                "Install: pip install pandas_ta"
            )
    return _TA


def compute(close: pd.Series, name: str, period: int, **kwargs) -> pd.Series:
    """Compute a single indicator using pandas_ta (TradingView-aligned).

    Supported names: sma, ema, rsi, atr, macd, bb, bbw, kc, kcw, adx, stoch, willr, cci, mfi, obv, wr, roc, mom, ts, vwap

    Returns a pd.Series aligned with the input index.
    """
    ta = _ensure_ta()
    name = name.lower().strip()

    if name == "sma":
        return ta.sma(close, length=period)
    elif name == "ema":
        return ta.ema(close, length=period)
    elif name == "rsi":
        return ta.rsi(close, length=period)
    elif name == "atr":
        high = kwargs.get("high")
        low = kwargs.get("low")
        if high is None or low is None:
            raise ValueError("atr requires high and low kwargs")
        return ta.atr(high, low, close, length=period)
    elif name == "macd":
        fast = kwargs.get("fast", 12)
        slow = kwargs.get("slow", 26)
        signal = kwargs.get("signal", 9)
        macd_df = ta.macd(close, fast=fast, slow=slow, signal=signal)
        key = kwargs.get("component", "MACD_12_26_9")
        return macd_df[key] if key in macd_df.columns else macd_df.iloc[:, 0]
    elif name == "bb":
        std = kwargs.get("std", 2.0)
        bb_df = ta.bbands(close, length=period, std=std)
        key = kwargs.get("component", "BBU_20_2.0")
        return bb_df[key] if key in bb_df.columns else bb_df.iloc[:, 0]
    elif name == "bbw":
        std = kwargs.get("std", 2.0)
        bb_df = ta.bbands(close, length=period, std=std)
        return bb_df[f"BBB_{period}_{std}"] if f"BBB_{period}_{std}" in bb_df.columns else bb_df.iloc[:, 2]
    elif name == "kc":
        kc_df = ta.kc(kwargs.get("high", close), kwargs.get("low", close), close, length=period)
        key = kwargs.get("component", "KCU_20_2")
        return kc_df[key] if key in kc_df.columns else kc_df.iloc[:, 0]
    elif name == "adx":
        high = kwargs.get("high")
        low = kwargs.get("low")
        if high is None or low is None:
            raise ValueError("adx requires high and low kwargs")
        adx_df = ta.adx(high, low, close, length=period)
        key = kwargs.get("component", f"ADX_{period}")
        return adx_df[key] if key in adx_df.columns else adx_df.iloc[:, 0]
    elif name == "stoch":
        high = kwargs.get("high")
        low = kwargs.get("low")
        if high is None or low is None:
            raise ValueError("stoch requires high and low kwargs")
        k = kwargs.get("k", 3)
        d = kwargs.get("d", 3)
        stoch_df = ta.stoch(high, low, close, k=period, d=k, smooth_k=d)
        key = kwargs.get("component", f"STOCHk_{period}_{k}_{d}")
        return stoch_df[key] if key in stoch_df.columns else stoch_df.iloc[:, 0]
    elif name == "willr":
        high = kwargs.get("high")
        low = kwargs.get("low")
        if high is None or low is None:
            raise ValueError("willr requires high and low kwargs")
        return ta.willr(high, low, close, length=period)
    elif name == "cci":
        high = kwargs.get("high")
        low = kwargs.get("low")
        if high is None or low is None:
            raise ValueError("cci requires high and low kwargs")
        return ta.cci(high, low, close, length=period)
    elif name == "mfi":
        high = kwargs.get("high")
        low = kwargs.get("low")
        volume = kwargs.get("volume")
        if high is None or low is None or volume is None:
            raise ValueError("mfi requires high, low, volume kwargs")
        return ta.mfi(high, low, close, volume, length=period)
    elif name == "obv":
        volume = kwargs.get("volume")
        if volume is None:
            raise ValueError("obv requires volume kwarg")
        return ta.obv(close, volume)
    elif name == "mom":
        return ta.mom(close, length=period)
    elif name == "roc":
        return ta.roc(close, length=period)
    elif name == "ts":
        # Ts = time series forecast (linear regression slope)
        return ta.tsignals(close, length=period, model="LR")

    raise ValueError(
        f"unknown indicator '{name}'; supported: "
        "sma, ema, rsi, atr, macd, bb, bbw, kc, adx, stoch, "
        "willr, cci, mfi, obv, mom, roc, ts"
    )


def validate(
    close: pd.Series,
    name: str,
    period: int,
    reference: pd.Series,
    tol: float = 1e-6,
    **kwargs,
) -> dict:
    """Compare our computed indicator against a reference series.

    Returns:
        {name, period, n, max_abs_error, mean_abs_error, matched, mismatches}
    """
    if name == "obv":
        # OBV needs volume
        ours = compute(close, name, period, **kwargs)
    else:
        ours = compute(close, name, period, **kwargs)
    df = pd.DataFrame({"ours": ours, "ref": reference}).dropna()
    diff = (df["ours"] - df["ref"]).abs()
    return {
        "name": name,
        "period": period,
        "n": int(len(df)),
        "max_abs_error": float(diff.max()) if len(diff) else 0.0,
        "mean_abs_error": float(diff.mean()) if len(diff) else 0.0,
        "matched": bool((diff <= tol).all()),
        "mismatches": int((diff > tol).sum()),
    }


# ── Legacy helpers (kept for backward compat with existing strategy code) ──


def sma(series: pd.Series, period: int) -> pd.Series:
    ta = _ensure_ta()
    return ta.sma(series, length=period)


def ema(series: pd.Series, period: int) -> pd.Series:
    ta = _ensure_ta()
    return ta.ema(series, length=period)


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    ta = _ensure_ta()
    return ta.rsi(series, length=period)


_INDICATORS = {
    "sma": lambda s, p, **kw: sma(s, p),
    "ema": lambda s, p, **kw: ema(s, p),
    "rsi": lambda s, p, **kw: rsi(s, p),
}


def compute_indicator(close: pd.Series, name: str, period: int, **kwargs) -> pd.Series:
    """Legacy gateway — prefer compute() for new code."""
    if name not in _INDICATORS:
        raise ValueError(f"unknown indicator {name}; supported: {list(_INDICATORS)}")
    return _INDICATORS[name](close, period, **kwargs)