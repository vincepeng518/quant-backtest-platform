import pandas as pd
from research.breakout_jev2.make_5m_csv import resample_5m


def test_resample_5m_aggregates_ohlc():
    idx = pd.date_range("2026-01-01 00:00", periods=10, freq="1min")
    raw = pd.DataFrame({
        "dt": idx,
        "open": range(10),
        "high": [i + 1 for i in range(10)],
        "low": [i - 1 for i in range(10)],
        "close": [i + 0.5 for i in range(10)],
        "vol": [1.0] * 10,
    })
    out = resample_5m(raw)
    assert list(out.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert len(out) == 2
    assert out["open"].iloc[0] == 0
    assert out["close"].iloc[0] == 4.5
    assert out["high"].iloc[0] == 5
    assert out["low"].iloc[0] == -1
    assert out["volume"].iloc[0] == 5.0
