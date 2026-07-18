#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pytest 驗證: research/trend_vol.py 的核心邏輯。
執行: cd /root/Crypto-Backtesting-Lab && source venv/bin/activate && pytest research/test_trend_vol.py -q
"""
import os
import sys
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import trend_vol as tv  # noqa: E402


def test_data_load_and_indicators():
    df = tv.load_data()
    assert len(df) > 1000, "data too small"
    assert {"open", "high", "low", "close"}.issubset(df.columns)

    df = tv.compute_indicators(df).dropna(subset=["bbw_pctile", "atr_eff"]).reset_index(drop=True)
    assert df["bbw"].notna().all() and (df["bbw"] > 0).all(), "bbw invalid"
    assert df["bbw_pctile"].between(0, 100).all(), "pctile out of range"
    assert df["atr_eff"].notna().all() and (df["atr_eff"] > 0).all(), "atr_eff invalid"
    assert df["bb_inside_kc"].dtype == bool, "bb_inside_kc not bool"


def test_signals_well_formed():
    df = tv.compute_indicators(tv.load_data()).dropna(subset=["bbw_pctile", "atr_eff"]).reset_index(drop=True)
    allowed = {"flat", "long", "short", "neutral"}
    for p, a in [(20, 0.03), (35, 0.025)]:
        s = df.apply(lambda r: tv.signal_at(r, p, a), axis=1)
        assert set(s.unique()).issubset(allowed), "bad signal_at"
    sq = df.apply(tv.signal_squeeze, axis=1)
    assert set(sq.unique()).issubset(allowed), "bad signal_squeeze"


def test_evaluate_finite():
    df = tv.compute_indicators(tv.load_data()).dropna(subset=["bbw_pctile", "atr_eff"]).reset_index(drop=True)
    ev = tv.evaluate(df, 35, 0.025)
    assert 0 <= ev["flat_precision"] <= 1
    assert 0 <= ev["trend_acc"] <= 1
    sqev = tv.evaluate_squeeze(df)
    assert 0 <= sqev["trend_acc"] <= 1


def test_threshold_monotonicity():
    df = tv.compute_indicators(tv.load_data()).dropna(subset=["bbw_pctile", "atr_eff"]).reset_index(drop=True)
    n_lo = tv.evaluate(df, 10, 0.025)["n_flat"]
    n_hi = tv.evaluate(df, 40, 0.025)["n_flat"]
    assert n_lo <= n_hi, "threshold monotonicity broken"
