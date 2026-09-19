"""橫斷面面板與訊號的單元測試。"""
import numpy as np
import pandas as pd

from research.breakout_jev2.lib_panel import (
    breakout_mask, cross_sectional_momentum_signal, squeeze_mask,
)


def _panel(n=300, k=5, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="4h")
    return pd.DataFrame(rng.normal(100, 1, size=(n, k)).cumsum(axis=0) + 100,
                        index=idx, columns=[f"S{i}" for i in range(k)])


def test_momentum_long_mask_only_top_quantile():
    C = _panel()
    lon, sho = cross_sectional_momentum_signal(C, lookback=20, top_q=0.2, bottom_q=0.2,
                                              min_universe=5)
    # top_q=0.2、5 檔 -> 每期最多 1 檔做多
    assert lon.sum(axis=1).max() <= 1
    assert sho.sum(axis=1).max() <= 1
    # 同一個時間點不能同時是 long 與 short
    assert not (lon & sho).any().any()


def test_momentum_does_not_use_future():
    C = _panel(n=100)
    lon1, _ = cross_sectional_momentum_signal(C, 20, min_universe=5)
    # 改動最後一根的價格不應影響更早的訊號
    C2 = C.copy()
    C2.iloc[-1] *= 5
    lon2, _ = cross_sectional_momentum_signal(C2, 20, min_universe=5)
    assert lon1.iloc[:-1].equals(lon2.iloc[:-1])


def test_breakout_mask_excludes_current_bar():
    C = pd.DataFrame({"A": [1.0, 2.0, 5.0]}, index=pd.date_range("2024-01-01", periods=3))
    H = pd.DataFrame({"A": [1.0, 2.0, 5.0]}, index=pd.date_range("2024-01-01", periods=3))
    m = breakout_mask(C, H, lookback=2)
    # 第 3 根：前 2 根最高 = 2.0，收盤 5.0 > 2.0 -> True（且沒把當根 5.0 算進去）
    assert bool(m.iloc[2, 0]) is True
    assert bool(m.iloc[1, 0]) is False


def test_squeeze_mask_is_low_when_bandwidth_tight():
    n = 300
    idx = pd.date_range("2024-01-01", periods=n, freq="4h")
    # 前 250 根大波動，後 50 根極小波動 -> 後段應該是壓縮
    a = np.concatenate([np.random.default_rng(1).normal(100, 5, 250),
                        np.random.default_rng(2).normal(100, 0.01, 50)])
    C = pd.DataFrame({"A": a}, index=idx)
    m = squeeze_mask(C, bandwidth_pctile=0.3, bb_len=20)
    assert m.iloc[-10:, 0].mean() > 0.5
