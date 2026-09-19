"""統計工具：bootstrap CI、蒙地卡羅、必要樣本量。"""
from __future__ import annotations

import numpy as np


def boot_ci(x: np.ndarray, n: int = 5000, seed: int = 11) -> tuple[float, float, float]:
    """回傳 (mean, 2.5%, 97.5%)。"""
    x = np.asarray(x, dtype=float)
    if len(x) < 5:
        return (float("nan"),) * 3
    rng = np.random.default_rng(seed)
    m = np.array([rng.choice(x, size=len(x), replace=True).mean() for _ in range(n)])
    return float(x.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def required_samples(trades_per_month: float, target_monthly: float, payoff: float,
                     fee_roundtrip: float, win_rate: float) -> float:
    """達到 target_monthly 月報酬所需的樣本量（保守估計，只用來說明差幾個數量級）。

    每筆期望 edge = win_rate*payoff - (1-win_rate) - fee_roundtrip（以風險單位計）
    所需每筆淨報酬率 r = (1+target)^(1/n_trades) - 1
    t=2 顯著所需樣本 n ≈ (2*sigma/r)^2，sigma 保守取 payoff。
    """
    if trades_per_month <= 0:
        return float("inf")
    r_needed = (1.0 + target_monthly) ** (1.0 / trades_per_month) - 1.0
    edge = win_rate * payoff - (1.0 - win_rate) - fee_roundtrip
    if edge <= 0:
        return float("inf")
    sigma = payoff
    return float((2.0 * sigma / max(r_needed, 1e-9)) ** 2)


def mc_paths(returns: np.ndarray, n_steps: int, n_sims: int, seed: int = 7) -> np.ndarray:
    """bootstrap 重抽樣產生 (n_sims, n_steps+1) 權益路徑。"""
    rng = np.random.default_rng(seed)
    r = np.asarray(returns, dtype=float)
    idx = rng.integers(0, len(r), size=(n_sims, n_steps))
    sampled = r[idx]
    paths = np.ones((n_sims, n_steps + 1), dtype=float)
    for k in range(n_steps):
        paths[:, k + 1] = np.maximum(paths[:, k] * (1.0 + sampled[:, k]), 0.0)
    return paths


def mc_summary(paths: np.ndarray, initial: float = 1.0,
               ruin_level: float = 0.5) -> dict[str, float]:
    final = paths[:, -1]
    peak = np.maximum.accumulate(paths, axis=1)
    dd = (peak - paths) / np.where(peak == 0, 1, peak)
    mdd = dd.max(axis=1)
    return {
        "median": float(np.median(final) * initial),
        "p5": float(np.percentile(final, 5) * initial),
        "p95": float(np.percentile(final, 95) * initial),
        "bankruptcy_prob_pct": float((final < ruin_level * initial).mean() * 100),
        "maxdd_median_pct": float(np.median(mdd) * 100),
        "maxdd_p95_pct": float(np.percentile(mdd, 95) * 100),   # 保守回撤估計（判定用）
        "var_95_pct": float((np.percentile(final, 5) - 1.0) * 100),
    }
