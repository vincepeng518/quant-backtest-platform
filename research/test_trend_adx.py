#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""驗證 trend_adx.py 的指標計算與回測邏輯。

執行：venv/bin/python -m pytest research/test_trend_adx.py -q
"""
import numpy as np
import pandas as pd

from trend_adx import compute_indicators, make_signal, evaluate, grid_search


def _synthetic_uptrend(n=60):
    open_, high, low, close, vol = [], [], [], [], []
    p = 100.0
    for _ in range(n):
        p += 1.0  # 嚴格上升
        open_.append(p)
        high.append(p + 0.5)
        low.append(p - 0.5)
        close.append(p)
        vol.append(1.0)
    return pd.DataFrame({
        'date': pd.date_range('2023-01-01', periods=n),
        'open': open_, 'high': high, 'low': low, 'close': close, 'volume': vol,
    })


def test_indicators_bounded_on_synthetic():
    d = compute_indicators(_synthetic_uptrend()).dropna(subset=['adx', 'macd_hist_slope']).reset_index(drop=True)
    assert (d['adx'] >= 0).all() and (d['adx'] <= 100).all(), 'ADX 必須在 [0,100]'
    assert (d['plus_di'] >= 0).all() and (d['plus_di'] <= 100).all(), '+DI 超出範圍'
    assert (d['minus_di'] >= 0).all() and (d['minus_di'] <= 100).all(), '-DI 超出範圍'


def test_uptrend_favors_plus_di():
    d = compute_indicators(_synthetic_uptrend()).dropna(subset=['adx']).reset_index(drop=True)
    assert d['plus_di'].mean() > d['minus_di'].mean(), '上升趨勢 +DI 應大於 -DI'


def test_signal_domain():
    d = compute_indicators(_synthetic_uptrend()).dropna(subset=['adx', 'macd_hist_slope']).reset_index(drop=True)
    sig = make_signal(d, 20, 25, 2.0, use_macd_confirm=True)
    assert set(sig.unique()).issubset({-1, 0, 1}), '信號只能是 {-1,0,1}'


def test_evaluate_bounds():
    d = compute_indicators(_synthetic_uptrend()).dropna(subset=['adx', 'macd_hist_slope']).reset_index(drop=True)
    sig = make_signal(d, 20, 25, 2.0, use_macd_confirm=True)
    ev, fr = evaluate(d, sig, n=5, flat_band=0.03)
    if ev['dir_acc'] == ev['dir_acc']:
        assert 0 <= ev['dir_acc'] <= 1
    if ev['flat_acc'] == ev['flat_acc']:
        assert 0 <= ev['flat_acc'] <= 1
    assert len(fr) == len(d)


def test_grid_search_shape():
    d = compute_indicators(_synthetic_uptrend()).dropna(subset=['adx', 'macd_hist_slope']).reset_index(drop=True)
    best, res = grid_search(d, n=5)
    assert len(best[0]) == 3, '最佳解應含 3 個參數'
    assert len(res) > 0
    assert {'adx_flat', 'adx_trend', 'di_diff', 'dir_acc', 'flat_acc', 'score'}.issubset(res.columns)
