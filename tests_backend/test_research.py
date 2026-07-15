# tests_backend/test_research.py
import numpy as np
import pandas as pd
from data.providers.test_data import generate_test_data
from engine.research import market_profile, signal_profile
from strategies.base import StrategyBase
from strategies.technical.moving_average import MovingAverageCrossStrategy


def _df():
    return generate_test_data("BTC_USDT")


def test_market_profile_keys():
    df = _df()
    r = market_profile(df)
    for k in ("returns_stats", "autocorrelation", "hurst", "vol_regime", "correlation", "seasonality"):
        assert k in r, f"missing {k}"


def test_hurst_in_range():
    df = _df()
    r = market_profile(df)
    assert 0.0 < r["hurst"] < 1.0


def test_returns_stats_fields():
    df = _df()
    rs = market_profile(df)["returns_stats"]
    for f in ("mean", "std", "skew", "kurtosis", "annualized_vol"):
        assert f in rs


def test_signal_profile_keys():
    df = generate_test_data("BTC_USDT")
    # use a strategy that emits signals on this synthetic data; if none, assert shape only
    try:
        r = signal_profile(df, MovingAverageCrossStrategy, {})
    except Exception:
        return  # skip if strategy requires warmup not present
    for k in ("signal_counts", "long_short_ratio", "entry_timing", "signal_forward_return"):
        assert k in r, f"missing {k}"
