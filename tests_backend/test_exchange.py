from engine.exchange import ExchangeModel

def test_maker_cheaper_than_taker():
    em = ExchangeModel(maker_fee=0.0002, taker_fee=0.0005)
    assert em.fee_for("limit", True) == 0.0002
    assert em.fee_for("market", False) == 0.0005
    assert em.fee_for("market", True) == 0.0005  # market is always taker

def test_thin_book_more_slippage():
    em = ExchangeModel(book_base_slippage=0.001)
    assert em.slippage_for(depth=10.0, qty=5.0) > em.slippage_for(depth=1000.0, qty=5.0)
    assert abs(em.slippage_for(depth=1000.0, qty=5.0) - 0.001 * (5/1000)) < 1e-12

def test_latency_and_fill():
    em = ExchangeModel(latency_bars=2)
    assert em.fill_delay_bars() == 2
    assert em.fill_probability(depth=100.0, qty=10.0) == 0.9
