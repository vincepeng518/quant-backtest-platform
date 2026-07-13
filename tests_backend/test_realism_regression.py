import pandas as pd
from engine.backtester import Backtester

class BuyHold:
    def __init__(self): self.position=None; self.params={}; self._closed=False
    def init(self,p): self.params=p
    def next(self,bar):
        from strategies.base import Signal
        # The engine syncs self.position back to the strategy each bar (backtester.py:209),
        # so we open once, close once, then stay flat -> exactly one completed trade.
        if self.position is None and not self._closed:
            return Signal(action="buy")
        if self.position is not None and not self._closed:
            self._closed = True
            return Signal(action="close")
        return None

def _df():
    return pd.DataFrame({"timestamp": pd.to_datetime([f"2024-01-0{i} 00:00" for i in range(1,6)]),
        "open":[100.,101.,102.,103.,104.],"high":[100.,101.,102.,103.,104.],
        "low":[100.,101.,102.,103.,104.],"close":[100.,101.,102.,103.,104.],"volume":[1.]*5})

def test_legacy_and_optin_identical():
    df = _df()
    # legacy default
    bt1 = Backtester(initial_capital=10000, commission=0.001, slippage=0.0005)
    bt1.set_data(df); s1=BuyHold(); s1.init({}); bt1.set_strategy(s1); r1 = bt1.run()
    # opt-in but all disabled
    bt2 = Backtester(initial_capital=10000, commission=0.001, slippage=0.0005,
                     funding=None, perp=None, leverage=1.0, exchange=None)
    bt2.set_data(df); s2=BuyHold(); s2.init({}); bt2.set_strategy(s2); r2 = bt2.run()
    assert len(r1.trades) == len(r2.trades) == 1
    assert abs(r1.trades[0].pnl - r2.trades[0].pnl) < 1e-9
    assert r2.trades[0].funding_paid == 0.0
    assert r2.trades[0].liquidated is False
