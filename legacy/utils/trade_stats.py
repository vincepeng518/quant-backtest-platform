"""
回測指標的單一真相來源（Single Source of Truth）

所有 UI 元件、KPI 卡片、績效計算都應該呼叫這個模組的函式來取得
n_trades / n_wins / win_rate，確保「分子（獲利筆數）/ 分母（總筆數）」
永遠跟顯示的勝率完全一致。

歷史問題：之前 backtester 的 metrics.win_rate 可能因資料或計算誤差產生
不一致（例：1 筆獲利 / 6 筆總數，metrics 卻顯示 33.33%），導致 UI 顯示
「1/6 但 33.33%」的矛盾。
"""
from __future__ import annotations

from typing import Dict, List, Any, Optional

import numpy as np
import pandas as pd


def _safe_len(obj) -> int:
    """安全取長度（支援 list / DataFrame / Series / None）。"""
    if obj is None:
        return 0
    try:
        return len(obj)
    except TypeError:
        return 0


def _count_winners_from_trades(trades: List[Dict]) -> int:
    """從 trades 列表直接數獲利交易筆數（pnl > 0）。"""
    if not trades:
        return 0
    count = 0
    for t in trades:
        if not isinstance(t, dict):
            continue
        pnl = t.get("pnl", None)
        if pnl is None:
            continue
        try:
            if float(pnl) > 0:
                count += 1
        except (TypeError, ValueError):
            continue
    return count


def _count_winners_from_trades_df(trades_df: pd.DataFrame) -> int:
    """從 trades_df 直接數獲利交易筆數（pnl > 0）。"""
    if trades_df is None or trades_df.empty or "pnl" not in trades_df.columns:
        return 0
    try:
        return int((trades_df["pnl"] > 0).sum())
    except Exception:
        return 0


def compute_trade_stats(
    result_df: Optional[pd.DataFrame] = None,
    trades: Optional[List[Dict]] = None,
    metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """計算 n_trades / n_wins / win_rate，統一來源避免不一致。

    優先順序（確保「分子 = 分母 × 比率」永遠成立）：
    1. 用 trades 列表實際計算（最準確，pnl > 0 直接 count）
    2. fallback 到 trades_df
    3. fallback 到 metrics 的 n_trades + 重新數 winners
    4. 全部都沒有 → 0

    參數：
        result_df: 回測結果 DataFrame（目前未使用，保留供未來擴充）
        trades: 交易明細 list[dict]
        metrics: backtester 回傳的指標 dict（可能含錯誤 win_rate）

    回傳：
        {
            "n_trades": int,   # 總平倉交易筆數
            "n_wins": int,     # 獲利交易筆數（pnl > 0）
            "win_rate": float, # 勝率 %（四捨五入到小數 2 位）
        }
    """
    metrics = metrics or {}

    # === 1. 從 trades 列表實際計算（最優先）===
    n_trades = _safe_len(trades)
    n_wins = _count_winners_from_trades(trades) if trades else 0

    # === 2. 如果 trades 是空的，但 metrics 有 n_trades 與 trades_df 可用 ===
    if n_trades == 0:
        n_trades = int(metrics.get("n_trades", 0) or 0)
        # 試圖從 metrics 提供的衍生欄位推算（避免再次使用錯誤的 win_rate）
        # 這裡不再信任 metrics.win_rate，只用 n_trades 與 n_wins 計算新 win_rate
        if n_wins == 0 and "n_winning_trades" in metrics:
            try:
                n_wins = int(metrics.get("n_winning_trades", 0) or 0)
            except (TypeError, ValueError):
                n_wins = 0

    # === 3. 計算 win_rate（統一用上面算的 n_trades / n_wins）===
    if n_trades > 0:
        win_rate_raw = (n_wins / n_trades) * 100.0
    else:
        win_rate_raw = 0.0

    # 四捨五入到小數 2 位
    win_rate = round(win_rate_raw, 2)

    return {
        "n_trades": int(n_trades),
        "n_wins": int(n_wins),
        "win_rate": float(win_rate),
    }


def compute_win_rate_only(
    trades: Optional[List[Dict]] = None,
    trades_df: Optional[pd.DataFrame] = None,
    metrics: Optional[Dict[str, Any]] = None,
) -> float:
    """便利函式：只回傳 win_rate（%）。

    與 compute_trade_stats 用相同的邏輯，確保一致。
    """
    stats = compute_trade_stats(trades=trades, metrics=metrics)
    if stats["n_trades"] == 0 and trades_df is not None:
        # 補一個 trades_df 的路徑
        n_t = len(trades_df)
        n_w = _count_winners_from_trades_df(trades_df)
        if n_t > 0:
            return round((n_w / n_t) * 100.0, 2)
    return stats["win_rate"]
