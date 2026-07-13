import pandas as pd
from engine.backtester import Backtester
from engine.funding import FundingModel, FundingSchedule
from engine.exchange import ExchangeModel
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


class LongStrat:
    def __init__(self): self.position=None; self.params={}
    def init(self,p): self.params=p
    def next(self,bar):
        if self.position is None:
            from strategies.base import Signal
            return Signal(action="buy")
        return None

def test_10x_long_liquidated_on_wick():
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01 00:00","2024-01-01 01:00","2024-01-01 02:00"]),
        "open":[100.0,100.0,90.0],"high":[100.0,100.0,90.5],"low":[100.0,100.0,89.0],
        "close":[100.0,100.0,90.0],"volume":[1.0,1.0,1.0]})
    from engine.perpetual import PerpSimulator
    bt = Backtester(initial_capital=10000, commission=0.0, slippage=0.0, perp=PerpSimulator(0.005), leverage=10.0)
    bt.set_data(df); s=LongStrat(); s.init({}); bt.set_strategy(s)
    r = bt.run()
    # 10x long entry 100; liq ~90.05; bar2 low 89 < liq => liquidated
    assert len(r.trades) == 1
    assert r.trades[0].liquidated is True
    # pnl = size*(liq_mark - entry); size = 10000*10/100 = 1000; mark 89 => 1000*(89-100) = -11000
    assert abs(r.trades[0].pnl - (-11000.0)) < 1e-6


class MktStrat:
    def __init__(self): self.position=None; self.params={}
    def init(self,p): self.params=p
    def next(self,bar):
        if self.position is None:
            return Signal(action="buy")
        return Signal(action="close")

def test_exchange_taker_fee_applied():
    # MktStrat emits default market signals -> taker fee path. Isolate from slippage.
    df = pd.DataFrame({"timestamp": pd.to_datetime(["2024-01-01 00:00","2024-01-01 08:00","2024-01-01 16:00"]),
        "open":[100.,101.,102.],"high":[100.,101.,102.],"low":[100.,101.,102.],"close":[100.,101.,102.],"volume":[1.,1.,1.]})
    em = ExchangeModel(maker_fee=0.0001, taker_fee=0.0002, latency_bars=0, book_base_slippage=0.0)
    bt = Backtester(initial_capital=10000, commission=0.001, slippage=0.0, exchange=em)
    bt.set_data(df); s=MktStrat(); s.init({}); bt.set_strategy(s)
    r = bt.run()
    # entry@100 size=100; exit@101; taker fee 0.0002 per side.
    # Engine books open fee into capital (not Trade.pnl) and close fee into Trade.pnl:
    # open cost = 10000*0.0002 = 2.0 -> capital 9998; close fee = 9998*0.0002 = 1.9996
    # Trade.pnl = 100*(101-100) - 1.9996 = 98.0004
    assert len(r.trades) == 1
    assert abs(r.trades[0].pnl - 98.0004) < 1e-4
    assert r.trades[0].funding_paid == 0.0

def test_exchange_fee_cheaper_than_default_commission():
    # taker 0.0002 < default commission 0.001 => exchange should yield higher pnl
    df = pd.DataFrame({"timestamp": pd.to_datetime(["2024-01-01 00:00","2024-01-01 08:00","2024-01-01 16:00"]),
        "open":[100.,101.,102.],"high":[100.,101.,102.],"low":[100.,101.,102.],"close":[100.,101.,102.],"volume":[1.,1.,1.]})
    em = ExchangeModel(taker_fee=0.0002, book_base_slippage=0.0)
    bt = Backtester(initial_capital=10000, commission=0.001, slippage=0.0, exchange=em)
    bt.set_data(df); s=MktStrat(); s.init({}); bt.set_strategy(s)
    r = bt.run()
    assert r.trades[0].pnl > 96.0  # cheaper than 0.001 commission path (would be 100-20=80)

def test_latency_delays_fill():
    # latency_bars=2: buy bar0 executes bar2, close bar1 executes bar3
    df = pd.DataFrame({"timestamp": pd.to_datetime([f"2024-01-01 {h:02d}:00" for h in range(6)]),
        "open":[100.,100.,100.,100.,100.,105.],"high":[100.,100.,100.,100.,100.,105.],
        "low":[100.,100.,100.,100.,100.,105.],"close":[100.,100.,100.,100.,100.,105.],"volume":[1.]*6})
    em = ExchangeModel(latency_bars=2, book_base_slippage=0.0)
    bt = Backtester(initial_capital=10000, commission=0.0, slippage=0.0, exchange=em)
    bt.set_data(df); s=MktStrat(); s.init({}); bt.set_strategy(s)
    r = bt.run()
    assert len(r.trades) == 1
    # executed at bar2 close=100
    assert abs(r.trades[0].entry_price - 100.0) < 1e-6
