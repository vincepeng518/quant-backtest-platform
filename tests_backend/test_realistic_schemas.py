from app.models.schemas import (
    BacktestConfig, FundingConfig, PerpetualConfig, ExchangeConfig, TradeRecord, StrategyConfig,
)

def test_backtest_config_defaults_disable_realism():
    cfg = BacktestConfig(strategy=StrategyConfig(template_id="ma_cross"), symbol="BTCUSDT")
    assert cfg.funding.enabled is False
    assert cfg.perpetual.enabled is False
    assert cfg.perpetual.leverage == 1.0
    assert cfg.exchange.enabled is False
    assert cfg.commission == 0.001  # legacy unchanged

def test_realism_config_parses():
    cfg = BacktestConfig(
        strategy=StrategyConfig(template_id="ma_cross"), symbol="BTCUSDT",
        funding=FundingConfig(enabled=True, interval_hours=4),
        perpetual=PerpetualConfig(enabled=True, leverage=10.0),
        exchange=ExchangeConfig(enabled=True, maker_fee=0.0001, latency_bars=2),
    )
    assert cfg.funding.interval_hours == 4
    assert cfg.perpetual.leverage == 10.0
    assert cfg.exchange.latency_bars == 2

def test_signal_order_type_and_bar_mark_price():
    from strategies.base import Signal, Bar
    import pandas as pd
    sig = Signal(action="buy", order_type="limit")
    assert sig.order_type == "limit"
    bar = Bar(timestamp=pd.Timestamp("2024-01-01"), open=1, high=1, low=1, close=1, volume=1, mark_price=1.01)
    assert bar.mark_price == 1.01

def test_trade_record_new_fields():
    t = TradeRecord(entry_time="t", entry_price=1.0, size=1.0, funding_paid=0.5, liquidated=True)
    assert t.funding_paid == 0.5
    assert t.liquidated is True
