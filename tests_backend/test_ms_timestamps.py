import pandas as pd
from app.api.routes.data import _to_unix_ms

def test_ms_preserves_subsecond():
    ts = pd.Series(pd.to_datetime(["2024-01-01 00:00:00.123", "2024-01-01 00:00:01.500"]))
    ms = _to_unix_ms(ts)
    # 2024-01-01 00:00:00.123 UTC = 1704067200123 ms
    assert ms.iloc[0] == 1704067200123
    assert ms.iloc[1] == 1704067201500
    # verify it is NOT truncated to seconds (would be ...200 if seconds)
    assert ms.iloc[1] % 1000 != 0  # has sub-second component

def test_route_uses_ms():
    # import the module to ensure it imports with pandas
    import app.api.routes.data as d
    assert hasattr(d, "_to_unix_ms")
