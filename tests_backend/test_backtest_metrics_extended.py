"""P0 验证: PnL% TV 口径修正 + 扩充 TV 指标 (年化/Calmar/最大盈利/期望值/比率/持仓)."""
import pandas as pd
import pytest

from engine.backtester import Backtester, Trade


def _make_result(trades, equity=None, dd=None, days=30, initial=10000.0):
    if equity is None:
        equity = [initial, initial * 1.1, initial * 0.95, initial * 1.2]
    if dd is None:
        dd = [0.0, 0.0, 5.0, 0.0]
    ts = [pd.Timestamp("2024-01-01") + pd.Timedelta(days=i) for i in range(len(equity))]
    bt = Backtester(initial_capital=initial)
    return bt._calculate_metrics(trades, equity, dd, buy_hold_curve=equity, timestamps=ts)


def test_pnl_pct_uses_notional_not_capital():
    """PnL% 口径 = pnl / (size*entry_price), 不再用 /total capital."""
    t = Trade(
        entry_time=pd.Timestamp("2024-01-01"), entry_price=100.0, size=1.0,
        exit_time=pd.Timestamp("2024-01-02"), exit_price=110.0,
        pnl=10.0, pnl_pct=999.0,  # 旧口径错值, 应被覆盖
    )
    r = _make_result([t])
    # 正确口径: 10 / (1*100) * 100 = 10%
    assert abs(r.trades[0].pnl_pct - 10.0) < 1e-6


def test_pnl_pct_negative_short_notional():
    t = Trade(
        entry_time=pd.Timestamp("2024-01-01"), entry_price=200.0, size=0.5,
        exit_time=pd.Timestamp("2024-01-02"), exit_price=180.0,
        pnl=-10.0, pnl_pct=0.0, direction="short",
    )
    r = _make_result([t])
    # -10 / (0.5*200) * 100 = -10%
    assert abs(r.trades[0].pnl_pct - (-10.0)) < 1e-6


def test_extended_tv_metrics_present_and_sane():
    trades = [
        Trade(entry_time=pd.Timestamp("2024-01-01"), entry_price=100.0, size=1.0,
              exit_time=pd.Timestamp("2024-01-02"), exit_price=110.0, pnl=10.0, holding_bars=5),
        Trade(entry_time=pd.Timestamp("2024-01-03"), entry_price=100.0, size=1.0,
              exit_time=pd.Timestamp("2024-01-04"), exit_price=95.0, pnl=-5.0, holding_bars=3),
        Trade(entry_time=pd.Timestamp("2024-01-05"), entry_price=100.0, size=1.0,
              exit_time=pd.Timestamp("2024-01-06"), exit_price=120.0, pnl=20.0, holding_bars=7),
    ]
    r = _make_result(trades, days=6)
    # win/loss ratio = avg_win / |avg_loss| = 15 / 5 = 3.0
    assert abs(r.win_loss_ratio - 3.0) < 1e-6
    # largest win = 20
    assert r.largest_win == 20.0
    # expectancy = 0.667*15 - 0.333*5 ≈ 8.33
    assert r.expectancy > 8.0 and r.expectancy < 9.0
    # avg holding bars = (5+3+7)/3 = 5
    assert abs(r.avg_holding_bars - 5.0) < 1e-6
    # annualized positive (gained)
    assert r.annual_return_pct > 0
    # calmar = annual / max_dd (>0)
    assert r.calmar_ratio >= 0
    # trade freq = 3 trades / 3 days (4 timestamps => 3-day span) = 1.0
    assert abs(r.trade_freq - 1.0) < 1e-6


def test_no_trades_safe():
    r = _make_result([])
    assert r.win_loss_ratio == 0.0
    assert r.expectancy == 0.0
    assert r.avg_holding_bars == 0.0
