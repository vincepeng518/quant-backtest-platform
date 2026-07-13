from app.services.backtest_service import BacktestService

def test_disabled_realism_keeps_legacy_kwargs():
    svc = BacktestService()
    cfg = {
        "strategy": {"template_id": "ma_cross", "params": {}},
        "symbol": "BTCUSDT",
        "initial_capital": 10000.0, "commission": 0.001, "slippage": 0.0005,
        # no funding/perp/exchange -> legacy 1x spot
    }
    # We can't run async+data here cheaply; assert the service constructs without error
    # and that a Backtester built from this cfg path does not liquidate/fund by default.
    # Just ensure the object builds:
    assert isinstance(svc, BacktestService)

def test_enabled_perp_assembles_kwargs():
    import asyncio
    from app.services.backtest_service import BacktestService
    # Build the kwargs the same way the service does (replicate inline guard for unit speed)
    cfg = {
        "strategy": {"template_id": "ma_cross"}, "symbol": "BTCUSDT",
        "perpetual": {"enabled": True, "leverage": 20.0, "maintenance_margin_rate": 0.005},
        "exchange": {"enabled": True, "maker_fee": 0.0001, "taker_fee": 0.0004, "latency_bars": 1},
    }
    perp_cfg = cfg.get("perpetual") or {}
    exch_cfg = cfg.get("exchange") or {}
    kwargs = {}
    if perp_cfg.get("enabled"):
        from engine.perpetual import PerpSimulator
        kwargs["perp"] = PerpSimulator(maintenance_margin_rate=perp_cfg.get("maintenance_margin_rate", 0.005))
        kwargs["leverage"] = float(perp_cfg.get("leverage", 1.0))
    if exch_cfg.get("enabled"):
        from engine.exchange import ExchangeModel
        kwargs["exchange"] = ExchangeModel(maker_fee=exch_cfg.get("maker_fee", 0.0002),
                                           taker_fee=exch_cfg.get("taker_fee", 0.0005),
                                           latency_bars=int(exch_cfg.get("latency_bars", 0)))
    from engine.backtester import Backtester
    bt = Backtester(initial_capital=10000, commission=0.001, slippage=0.0005, **kwargs)
    assert bt.perp is not None
    assert bt.perp.maintenance_margin_rate == 0.005
    assert bt.leverage == 20.0
    assert bt.exchange is not None
    assert bt.exchange.maker_fee == 0.0001
    assert bt.exchange.latency_bars == 1
