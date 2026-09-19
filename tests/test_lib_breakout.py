"""突破引擎單元測試：出場方法行為必須正確，否則後續所有結果無意義。"""
import numpy as np
import pandas as pd
import pytest

from research.breakout_jev2.lib_breakout import backtest_breakout, metrics, prepare


def _df(n=400):
    """平台盤：don_hi=101（永不突破），除非測試自行改某一根。"""
    idx = pd.date_range("2020-01-01", periods=n, freq="4h")
    return pd.DataFrame({
        "timestamp": idx,
        "open": [100.0] * n, "high": [100.5] * n,
        "low": [99.5] * n, "close": [100.0] * n,
        "volume": [1.0] * n, "atr": [1.0] * n,
        "don_hi_96": [101.0] * n, "don_lo_96": [99.0] * n,
        "don_hi_48": [101.0] * n, "don_lo_48": [99.0] * n,
    })


def _breakout_df(n=400, at=100, block_after: bool = True):
    """在 index==at 觸發一次突破。block_after: 之後把通道推高，避免重複觸發。"""
    df = _df(n)
    df.loc[at, "close"] = 105.0
    df.loc[at, "don_hi_96"] = 100.0
    if block_after:
        df.loc[at + 1:, "don_hi_96"] = 1e9
        df.loc[at + 1:, "don_lo_96"] = -1e9
    return df


def test_no_breakout_no_trades():
    df = _df()
    tr, eq = backtest_breakout(df, lookback=96, exit_method="trail")
    assert len(tr) == 0
    assert eq[-1] == 1.0


def test_oco_takes_profit_at_target():
    df = _breakout_df()
    df.loc[101:250, "high"] = 130.0        # 觸及 target = 100 + 4*1
    tr, _ = backtest_breakout(df, lookback=96, exit_method="oco",
                              stop_atr=2.0, target_atr=4.0, fee=0.0, slippage=0.0)
    assert len(tr) == 1
    assert tr[0]["reason"] == "oco_tp"
    assert abs(tr[0]["exit"] - 104.0) < 1e-9


def test_trail_lets_winner_run_further_than_oco():
    """關鍵性質：移動停損必須讓趨勢單跑得比固定停利遠。"""
    df = _breakout_df()
    # 單調上升到 140 後回落
    for j in range(101, 180):
        px = 100 + (j - 100) * 0.4
        df.loc[j, ["open", "high", "low", "close"]] = [px, px + 0.3, px - 0.3, px]
    for j in range(180, 260):
        px = df.loc[179, "close"] - (j - 179) * 0.5
        df.loc[j, ["open", "high", "low", "close"]] = [px, px + 0.3, px - 0.3, px]
    tr_oco, _ = backtest_breakout(df, lookback=96, exit_method="oco",
                                  stop_atr=2.0, target_atr=4.0, fee=0.0, slippage=0.0)
    tr_tr, _ = backtest_breakout(df, lookback=96, exit_method="trail",
                                 stop_atr=2.0, trail_atr=3.0, fee=0.0, slippage=0.0)
    assert len(tr_oco) == 1 and len(tr_tr) == 1
    assert tr_tr[0]["ret"] > tr_oco[0]["ret"], "移動停損應該讓獲利跑更遠"


def test_donchian_exit_triggers_on_close_below_channel():
    df = _breakout_df()
    df.loc[101:149, "high"] = 106.0
    df.loc[101:149, "low"] = 104.5
    df.loc[101:149, "close"] = 105.5
    df.loc[150, ["open", "high", "low", "close"]] = [105.5, 105.5, 95.0, 96.0]
    df.loc[150, "don_lo_48"] = 100.0        # 收盤 96 < 100 -> 觸發
    tr, _ = backtest_breakout(df, lookback=96, exit_method="donchian",
                              exit_lookback=48, fee=0.0, slippage=0.0)
    assert len(tr) == 1
    assert tr[0]["reason"] == "donchian"


def test_short_direction_symmetry():
    """空單：跌破 don_lo 進場，方向必須是 -1。"""
    df = _df()
    df.loc[100, "close"] = 95.0
    df.loc[100, "don_lo_96"] = 100.0
    df.loc[101, "don_lo_96"] = 100.0
    df.loc[101:250, "low"] = 80.0           # 下跌 -> 空單獲利
    df.loc[102:, "don_lo_96"] = -1e9
    df.loc[102:, "don_hi_96"] = 1e9
    tr, _ = backtest_breakout(df, lookback=96, direction="short",
                              exit_method="trail", trail_atr=3.0, fee=0.0, slippage=0.0)
    assert len(tr) == 1
    assert tr[0]["dir"] == -1
    assert tr[0]["ret"] > 0


def test_fee_and_slippage_reduce_return():
    df = _breakout_df()
    df.loc[101:250, "high"] = 130.0
    tr0, _ = backtest_breakout(df, lookback=96, exit_method="oco",
                               fee=0.0, slippage=0.0)
    tr1, _ = backtest_breakout(df, lookback=96, exit_method="oco",
                               fee=0.0005, slippage=0.0002)
    assert tr0[0]["ret"] - tr1[0]["ret"] == pytest.approx(0.0005 * 2 + 0.0002 * 2, abs=1e-9)


def test_max_hold_forces_exit():
    df = _breakout_df()
    df.loc[101:399, "high"] = 100.5         # 永不觸停利也不觸停損
    df.loc[101:399, "low"] = 99.5
    df.loc[101:399, "close"] = 100.0
    tr, _ = backtest_breakout(df, lookback=96, exit_method="time", max_hold=20,
                              fee=0.0, slippage=0.0)
    assert len(tr) == 1
    assert tr[0]["bars"] == 19              # 進場後第 20 根出場（index e..e+19）
    assert tr[0]["reason"] == "max_hold"


def test_metrics_sharpe_positive_for_winning_system():
    rng = np.random.default_rng(0)
    tr = [{"i": k, "dir": 1, "ret": float(0.02 + rng.normal(0, 0.005)), "bars": 10,
           "reason": "x"} for k in range(50)]
    eq = np.ones(100)
    m = metrics(tr, eq, 100, bars_per_year=2190)
    assert m["sharpe"] > 0
    assert m["n"] == 50
    assert m["wr"] == 1.0
    assert m["payoff"] > 0


def test_prepare_is_causal():
    n = 300
    df = pd.DataFrame({
        "timestamp": pd.date_range("2020-01-01", periods=n, freq="4h"),
        "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1.0,
    })
    df.loc[200, "high"] = 1000.0            # 巨量長影線
    out = prepare(df, [96], [48])
    assert out.loc[200, "don_hi_96"] == 100.0   # 不含當根
    assert out.loc[201, "don_hi_96"] == 1000.0  # 下一根才反映
