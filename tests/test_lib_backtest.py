import numpy as np
import os
import pandas as pd
from research.breakout_jev2.lib_backtest import backtest, load_env, run_grid


def test_load_env_reads_dotenv_file(tmp_path, monkeypatch):
    p = tmp_path / "envfile"
    p.write_text("# comment\nAI_GATEWAY_API_KEY=abc123\n")
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    load_env(str(p))
    assert os.environ["AI_GATEWAY_API_KEY"] == "abc123"


def _flat_df(n=300, don_hi=999.0):
    """預設不觸發突破（don_hi 遠高於 close）；要測訊號的測試自行改特定 bar。"""
    idx = pd.date_range("2026-01-01", periods=n, freq="5min")
    return pd.DataFrame({
        "timestamp": idx,
        "open": [100.0] * n, "high": [100.5] * n,
        "low": [99.5] * n, "close": [100.0] * n,
        "volume": [1.0] * n, "atr": [1.0] * n,
        "don_hi": [don_hi] * n, "don_lo": [1.0] * n,
    })


def _one_breakout_df(n=300, at=100):
    """只有 index==at 那一根突破（其餘 don_hi 極高 -> 不再發訊號）。"""
    df = _flat_df(n)
    df.loc[at, "close"] = 105.0
    df.loc[at, "don_hi"] = 99.0
    return df


def test_no_signal_no_trades():
    df = _flat_df()
    tr, eq = backtest(df, lookback=96, stop_atr=2.0, target_atr=4.0, brk_max=1.0)
    assert len(tr) == 0
    assert eq[-1] == 1.0


def test_fee_reduces_return_by_2x_rate():
    """單筆強制進場：無成本 vs 有成本，差距 = 2*fee*leverage。"""
    df = _one_breakout_df()
    df.loc[101:220, "high"] = 120.0          # 保證碰到停利
    tr0, _ = backtest(df, 96, 2.0, 4.0, 10.0, fee=0.0, slippage=0.0)
    tr1, _ = backtest(df, 96, 2.0, 4.0, 10.0, fee=0.0005, slippage=0.0)
    assert len(tr0) == 1 and len(tr1) == 1
    assert abs((tr0[0]["ret"] - tr1[0]["ret"]) - 0.001) < 1e-9


def test_leverage_scales_pnl_linearly_before_liquidation():
    df = _one_breakout_df()
    df.loc[101:220, "high"] = 120.0
    tr1, _ = backtest(df, 96, 2.0, 4.0, 10.0, fee=0.0, leverage=1)
    tr5, _ = backtest(df, 96, 2.0, 4.0, 10.0, fee=0.0, leverage=5)
    assert len(tr1) == 1 and len(tr5) == 1
    assert abs(tr5[0]["ret"] - 5 * tr1[0]["ret"]) < 1e-9


def test_liquidation_zeros_equity():
    """10x、逆勢 12% 必然爆倉（維持保證金 0.5%）。"""
    df = _one_breakout_df()
    df.loc[101:150, "low"] = 80.0            # 反向 24% -> 爆倉
    tr, eq = backtest(df, 96, 2.0, 4.0, 10.0, fee=0.0, leverage=10)
    assert len(tr) == 1
    assert tr[0]["liq"] is True
    assert eq[-1] <= 1e-9


def test_stop_loss_exits_at_stop_price():
    df = _one_breakout_df()
    df.loc[101:220, "low"] = 90.0            # 觸及 stop（entry 100 - 2*1 = 98）
    tr, _ = backtest(df, 96, 2.0, 4.0, 10.0, fee=0.0, slippage=0.0)
    assert len(tr) == 1
    assert abs(tr[0]["exit"] - 98.0) < 1e-9
    assert tr[0]["liq"] is False


def test_grid_runs_parallel_and_returns_sorted_by_sharpe():
    df = pd.concat([_flat_df()] * 2, ignore_index=True)
    df.loc[300, "close"] = 105.0
    grid = [(96, 2.0, 4.0, 1.0), (96, 1.0, 6.0, 1.0)]
    res = run_grid(df, grid, workers=2)
    assert len(res) == 2
    assert res[0]["sharpe"] >= res[1]["sharpe"]
