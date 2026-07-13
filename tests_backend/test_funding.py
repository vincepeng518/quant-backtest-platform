import pandas as pd
from engine.funding import FundingModel, FundingSchedule

def test_accrual_over_two_intervals():
    idx = pd.to_datetime(["2024-01-01 00:00", "2024-01-01 08:00", "2024-01-01 16:00"])
    rates = pd.Series([0.0001, -0.0002, 0.0001], index=idx)
    fm = FundingModel(FundingSchedule(interval_hours=8, rates=rates))
    accrued = fm.accrued(pd.Timestamp("2024-01-01 00:00"), pd.Timestamp("2024-01-01 16:00"), side=1)
    # long through 08:00 (+0.0001) and 16:00 (-0.0002) payments => net -0.0001
    assert abs(accrued - (-0.0001)) < 1e-12
