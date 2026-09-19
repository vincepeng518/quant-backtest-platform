import numpy as np
import pandas as pd
from research.breakout_jev2.lib_data import add_atr, add_features, prior_extremes, load_5m


def test_add_atr_has_no_nan_after_warmup():
    df = load_5m("BTC_USDT")
    df = add_atr(df, n=14)
    assert df["atr"].isna().sum() == 13
    assert (df["atr"].dropna() > 0).all()


def test_prior_extremes_excludes_current_bar():
    df = pd.DataFrame({"high": [1.0, 2.0, 5.0], "low": [1.0, 0.5, 0.1]})
    hi, lo = prior_extremes(df, lookback=2)
    # index 2 的前 2 根 = [1,2] / [1,0.5]，不含當根 5.0 / 0.1
    assert hi.iloc[2] == 2.0
    assert lo.iloc[2] == 0.5
    assert np.isnan(hi.iloc[1])


def test_add_features_creates_one_channel_per_lookback():
    df = load_5m("BTC_USDT").head(800).copy()
    out = add_features(df, lookbacks=[24, 96])
    assert "don_hi_24" in out.columns and "don_hi_96" in out.columns
    # 24 根通道必定 <= 96 根通道（更短窗更貼近價格）
    valid = out.dropna(subset=["don_hi_24", "don_hi_96"])
    assert (valid["don_hi_24"] <= valid["don_hi_96"]).all()


def test_features_are_causal():
    """lookback 越大，don_hi 不可能包含當根（用單根極大值驗證）。"""
    df = load_5m("BTC_USDT").head(500).copy()
    df = add_atr(df)
    df.loc[400, "high"] = df["high"].max() * 2
    hi, _ = prior_extremes(df, lookback=96)
    assert hi.iloc[400] < df.loc[400, "high"]
