"""lib_funding 測試：時間軸正確性、as-of 對齊不引入未來資訊。"""
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, "/root/Crypto-Backtesting-Lab")
from research.breakout_jev2.lib_funding import (EPOCH, INTERVAL_H, align_to_bars,
                                                available_funding, load_funding)


def test_available_has_btc_and_no_summary():
    syms = available_funding()
    assert "BTCUSDT" in syms
    assert not any(s.startswith("_") for s in syms), "_summary 應被排除"
    assert len(syms) >= 10


def test_load_funding_shape_and_epoch():
    s = load_funding("BTCUSDT")
    assert len(s) == 3295
    assert s.index[0] == EPOCH
    assert (s.index[1] - s.index[0]) == pd.Timedelta(hours=INTERVAL_H)
    assert s.notna().all()


def test_load_funding_missing_raises():
    with pytest.raises(FileNotFoundError):
        load_funding("NOTACOINUSDT")


def test_align_uses_last_known_value():
    """K 線時間軸上的每個點應拿到「不晚於它」的最後一筆 funding。"""
    fund = pd.Series([0.001, 0.002, 0.003],
                     index=pd.DatetimeIndex(["2024-01-01 00:00",
                                             "2024-01-01 08:00",
                                             "2024-01-01 16:00"]))
    idx = pd.DatetimeIndex(["2024-01-01 00:00",   # 恰好在費率點上
                            "2024-01-01 04:00",   # 用 00:00 的值
                            "2024-01-01 08:00",   # 用 08:00 的值
                            "2024-01-01 12:00"])  # 用 08:00 的值
    out = align_to_bars(fund, idx)
    assert out.iloc[0] == pytest.approx(0.001)
    assert out.iloc[1] == pytest.approx(0.001)
    assert out.iloc[2] == pytest.approx(0.002)
    assert out.iloc[3] == pytest.approx(0.002)


def test_align_no_lookahead():
    """第一筆費率之前的時間點必須是 NaN，不可回填未來值。"""
    fund = pd.Series([0.001, 0.002],
                     index=pd.DatetimeIndex(["2024-01-01 00:00", "2024-01-01 08:00"]))
    idx = pd.DatetimeIndex(["2023-12-31 20:00",   # 早於所有費率 → NaN
                            "2024-01-01 00:00"])
    out = align_to_bars(fund, idx)
    assert np.isnan(out.iloc[0]), "早於資料起點必須是 NaN（不可 bfill）"
    assert out.iloc[1] == pytest.approx(0.001)


def test_align_stale_guard():
    """超過 max_stale_h 沒有更新的點應為 NaN。"""
    fund = pd.Series([0.001], index=pd.DatetimeIndex(["2024-01-01 00:00"]))
    idx = pd.DatetimeIndex(["2024-01-01 04:00",    # 4h 內 → 有效
                            "2024-01-03 00:00"])   # 48h → 超過門檻
    out = align_to_bars(fund, idx, max_stale_h=8)
    assert out.iloc[0] == pytest.approx(0.001)
    assert np.isnan(out.iloc[1])
