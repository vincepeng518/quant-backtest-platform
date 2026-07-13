import pandas as pd
from engine.backtester import Backtester
from engine.funding import FundingModel, FundingSchedule
from strategies.base import Signal

def _make_df():
    return pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01 00:00","2024-01-01 08:00","2024-01-01 16:00"]),
        "open":[100.0,101.0,102.0],"high":[100.0,101.0,102.0],
        "low":[100.0,101.0,102.0],"close":[100.0,101.0,102.0],"volume":[1.0,1.0,1.0]})

class BuyHoldStrat:
    def __init__(self): self.position=None; self.params={}
    def init(self,p): self.params=p
    def next(self,bar):
        if self.position is None:
            return Signal(action="buy")
        return Signal(action="close")

def test_funding_reduces_long_pnl():
    df = _make_df()
    idx = pd.to_datetime(["2024-01-01 08:00"])
    fm = FundingModel(FundingSchedule(8, pd.Series([0.001], index=idx)))
    bt = Backtester(initial_capital=10000, commission=0.0, slippage=0.0, funding=fm)
    bt.set_data(df)
    s = BuyHoldStrat(); s.init({}); bt.set_strategy(s)
    r = bt.run()
    # BuyHoldStrat opens at bar0 (close=100) and closes at bar1 (close=101):
    # gross pnl = (101-100)*100units = 100; funding long held through 08:00 pays
    # 0.001*notional(100*100=10000) = 10. Net pnl = 100 - 10 = 90.
    assert len(r.trades) == 1
    assert abs(r.trades[0].pnl - (100 - 10)) < 1e-6
    assert abs(r.trades[0].funding_paid - 10.0) < 1e-6
