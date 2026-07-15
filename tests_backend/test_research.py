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
    r = signal_profile(df, MovingAverageCrossStrategy, {})
    # top-level keys
    for k in ("signal_counts", "long_short_ratio", "entry_timing", "signal_forward_return"):
        assert k in r, f"missing {k}"
    # nested structure
    assert isinstance(r["signal_counts"], dict), "signal_counts must be a dict"
    assert isinstance(r["long_short_ratio"], float), "long_short_ratio must be a float"
    et = r["entry_timing"]
    assert isinstance(et["mean_percentile"], float), "entry_timing.mean_percentile must be a float"
    assert et["samples"] > 0, "entry_timing should have samples on data that emits signals"
    sfr = r["signal_forward_return"]
    assert isinstance(sfr["mean"], float), "signal_forward_return.mean must be a float"
    assert isinstance(sfr["n"], int), "signal_forward_return.n must be an int"
    # if the strategy emits no buy/sell signals the profile is meaningless -> fail loudly
    emitted = sum(v for k, v in r["signal_counts"].items() if k in ("buy", "sell"))
    assert emitted > 0, "MovingAverageCrossStrategy should emit entry signals on this data"
