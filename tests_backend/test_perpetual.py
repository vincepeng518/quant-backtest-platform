from engine.perpetual import PerpSimulator

def test_liquidation_on_wick():
    ps = PerpSimulator(maintenance_margin_rate=0.005)
    # 10x long entry 100. liq = 100*(1 - 0.995/10) = 100*(1-0.0995)=90.05
    assert ps.check_liquidation(mark_price=91.0, entry_price=100.0, size=1.0, leverage=10.0) is False
    assert ps.check_liquidation(mark_price=90.0, entry_price=100.0, size=1.0, leverage=10.0) is True

def test_short_liquidation():
    ps = PerpSimulator(maintenance_margin_rate=0.005)
    # 10x short entry 100. liq = 100*(1 + 0.0995)=109.95
    assert ps.check_liquidation(mark_price=109.0, entry_price=100.0, size=-1.0, leverage=10.0) is False
    assert ps.check_liquidation(mark_price=110.0, entry_price=100.0, size=-1.0, leverage=10.0) is True

def test_margin_required():
    ps = PerpSimulator()
    assert abs(ps.margin_required(10000.0, 10.0) - 1000.0) < 1e-9
