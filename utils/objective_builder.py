"""
目標函數（Objective Function）建構器

支援多種績效指標作為優化目標：
- sharpe_ratio（預設）
- calmar_ratio
- profit_factor
- cagr_minus_half_maxdd
- sortino_ratio
- custom_risk_adjusted
"""
from __future__ import annotations

from typing import Dict, Callable, Optional, Any
import numpy as np
import pandas as pd


# === 預設目標函數 ===

def metric_sharpe_ratio(metrics: Dict[str, Any], risk_free_rate: float = 0.0) -> float:
    """Sharpe Ratio：風險調整後報酬（越高越好）"""
    return float(metrics.get("sharpe_ratio", 0.0) or 0.0)


def metric_sortino_ratio(metrics: Dict[str, Any]) -> float:
    """Sortino Ratio：只懲罰下行波動"""
    return float(metrics.get("sortino_ratio", 0.0) or 0.0)


def metric_calmar_ratio(metrics: Dict[str, Any]) -> float:
    """Calmar Ratio：年化報酬 / 最大回撤"""
    return float(metrics.get("calmar_ratio", 0.0) or 0.0)


def metric_profit_factor(metrics: Dict[str, Any]) -> float:
    """Profit Factor：總利潤 / 總虧損"""
    pf = metrics.get("profit_factor", 0.0) or 0.0
    # 轉成 float，負值轉成 0
    return float(pf) if pf > 0 else 0.0


def metric_total_return(metrics: Dict[str, Any]) -> float:
    """總報酬率（%）"""
    return float(metrics.get("total_return_pct", 0.0) or 0.0)


def metric_cagr_minus_half_maxdd(metrics: Dict[str, Any]) -> float:
    """
    複合指標：CAGR - 0.5 * MaxDD
    鼓勵高成長同時懲罰大回撤
    """
    cagr = float(metrics.get("cagr_pct", 0.0) or 0.0)
    maxdd = float(metrics.get("max_drawdown_pct", 0.0) or 0.0)
    return cagr - 0.5 * maxdd


def metric_risk_adjusted(metrics: Dict[str, Any],
                          return_weight: float = 1.0,
                          dd_weight: float = 0.5,
                          trades_weight: float = 0.1) -> float:
    """
    通用風險調整指標
    score = return_weight * return_pct - dd_weight * max_dd_pct + trades_weight * min(n_trades, 50)
    """
    ret = float(metrics.get("total_return_pct", 0.0) or 0.0)
    dd = float(metrics.get("max_drawdown_pct", 0.0) or 0.0)
    n = int(metrics.get("n_trades", 0) or 0)
    return return_weight * ret - dd_weight * dd + trades_weight * min(n, 50)


def metric_win_rate(metrics: Dict[str, Any]) -> float:
    """勝率（%）"""
    return float(metrics.get("win_rate", 0.0) or 0.0)


def metric_expectancy(metrics: Dict[str, Any]) -> float:
    """期望值：平均每筆交易報酬率"""
    return float(metrics.get("expectancy_pct", 0.0) or 0.0)


# === 目標函數註冊表 ===

OBJECTIVE_REGISTRY: Dict[str, Callable[[Dict[str, Any]], float]] = {
    "sharpe_ratio": metric_sharpe_ratio,
    "sortino_ratio": metric_sortino_ratio,
    "calmar_ratio": metric_calmar_ratio,
    "profit_factor": metric_profit_factor,
    "total_return": metric_total_return,
    "cagr_minus_half_maxdd": metric_cagr_minus_half_maxdd,
    "risk_adjusted": metric_risk_adjusted,
    "win_rate": metric_win_rate,
    "expectancy": metric_expectancy,
}


def get_objective_fn(name: str) -> Callable[[Dict[str, Any]], float]:
    """
    取得目標函數

    Args:
        name: 目標函數名稱

    Returns:
        函數：metrics -> float

    Raises:
        ValueError: 不支援的目標
    """
    if name not in OBJECTIVE_REGISTRY:
        raise ValueError(
            f"不支援的目標函數: {name}。"
            f"可用: {list(OBJECTIVE_REGISTRY.keys())}"
        )
    return OBJECTIVE_REGISTRY[name]


def list_objectives() -> list:
    """列出所有可用的目標函數"""
    return list(OBJECTIVE_REGISTRY.keys())


def custom_objective(
    metrics: Dict[str, Any],
    formula: str = "sharpe_ratio",
) -> float:
    """
    從公式字串計算目標值

    支援運算子: + - * / ( ) 和指標名稱
    範例: "cagr - 0.5 * max_drawdown_pct"
    """
    # 安全白名單替換
    safe = formula
    replacements = {
        "sharpe_ratio": f"({metrics.get('sharpe_ratio', 0)})",
        "total_return_pct": f"({metrics.get('total_return_pct', 0)})",
        "cagr_pct": f"({metrics.get('cagr_pct', 0)})",
        "max_drawdown_pct": f"({metrics.get('max_drawdown_pct', 0)})",
        "win_rate": f"({metrics.get('win_rate', 0)})",
        "profit_factor": f"({metrics.get('profit_factor', 0)})",
        "calmar_ratio": f"({metrics.get('calmar_ratio', 0)})",
        "n_trades": f"({metrics.get('n_trades', 0)})",
    }
    for k, v in replacements.items():
        safe = safe.replace(k, v)

    # 僅允許數字、運算子、括號、小數點
    import re
    if re.search(r"[^0-9+\-*/().\s]", safe):
        raise ValueError(f"公式包含不允許的字元: {formula}")

    try:
        return float(eval(safe))
    except Exception as e:
        raise ValueError(f"公式求值失敗: {formula} -> {safe} ({e})")


__all__ = [
    "OBJECTIVE_REGISTRY",
    "get_objective_fn",
    "list_objectives",
    "metric_sharpe_ratio",
    "metric_sortino_ratio",
    "metric_calmar_ratio",
    "metric_profit_factor",
    "metric_total_return",
    "metric_cagr_minus_half_maxdd",
    "metric_risk_adjusted",
    "metric_win_rate",
    "metric_expectancy",
    "custom_objective",
]
