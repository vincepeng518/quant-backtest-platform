"""
蒙地卡羅模擬模組
透過隨機重排交易順序，評估策略的穩健性與風險

核心概念：
- 保留每筆交易的 PnL（時間資訊丟棄）
- 隨機重排 N 次
- 每次產生新的權益曲線
- 統計所有可能結果的分布
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
import random


class MonteCarloSimulator:
    """
    蒙地卡羅交易模擬器

    使用方式：
    sim = MonteCarloSimulator(initial_capital=10000)
    results = sim.run(trades, n_simulations=1000)
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        random_seed: int = None,
    ):
        self.initial_capital = initial_capital
        if random_seed is not None:
            np.random.seed(random_seed)
            random.seed(random_seed)

    def run(
        self,
        trades: List[Dict],
        n_simulations: int = 1000,
        method: str = "shuffle",  # "shuffle" 或 "bootstrap"
        max_loss_pct: float = 50.0,  # 破產門檻：虧損超過 X% 視為破產
    ) -> Dict:
        """
        執行蒙地卡羅模擬

        trades: 交易清單（從回測引擎得到）
        n_simulations: 模擬次數
        method: shuffle=重排 / bootstrap=有放回抽樣
        max_loss_pct: 破產判定門檻

        回傳：
        - equity_curves: shape=(n_simulations, n_trades) 的權益矩陣
        - drawdowns: shape=(n_simulations, n_trades) 的回撤矩陣
        - final_returns: 每個模擬的最終報酬率
        - max_drawdowns: 每個模擬的最大回撤
        - ruin_prob: 破產機率
        - percentiles: 各分位數
        """
        if not trades or len(trades) < 2:
            return {"error": "交易數不足（需要至少 2 筆）"}

        # 提取每筆交易的 PnL 百分比
        pnl_pcts = np.array([t["pnl_pct"] for t in trades])
        n_trades = len(pnl_pcts)

        equity_curves = np.zeros((n_simulations, n_trades + 1))
        equity_curves[:, 0] = self.initial_capital
        max_drawdowns = np.zeros(n_simulations)
        final_returns = np.zeros(n_simulations)
        # 計算「路徑差異」用：peak 達到時間
        time_to_peak = np.zeros(n_simulations)
        ruin_count = 0
        ruin_threshold = self.initial_capital * (1 - max_loss_pct / 100)

        for i in range(n_simulations):
            if method == "shuffle":
                # 重排：每筆交易 PnL 不變，但順序隨機
                shuffled = pnl_pcts.copy()
                np.random.shuffle(shuffled)
            elif method == "bootstrap":
                # Bootstrap：有放回抽樣
                shuffled = np.random.choice(pnl_pcts, size=n_trades, replace=True)
            else:
                raise ValueError(f"未知方法: {method}")

            # 計算權益曲線
            equity = self.initial_capital
            peak = self.initial_capital
            peak_time = 0
            for j, pnl_pct in enumerate(shuffled):
                equity *= (1 + pnl_pct)
                equity_curves[i, j + 1] = equity

                # 記錄達到 peak 的時間
                if equity > peak:
                    peak = equity
                    peak_time = j + 1

                # 檢查破產
                if equity <= ruin_threshold:
                    ruin_count += 1
                    break  # 破產了，剩餘填 0

            # 如果破產了，剩餘值保持 0
            final_returns[i] = (equity_curves[i, -1] / self.initial_capital - 1) * 100
            max_drawdowns[i] = self._calc_max_drawdown(equity_curves[i])
            time_to_peak[i] = peak_time

        # 計算分位數
        percentiles = self._calc_percentiles(final_returns, max_drawdowns)

        return {
            "equity_curves": equity_curves,
            "final_returns": final_returns,
            "max_drawdowns": max_drawdowns,
            "ruin_prob": ruin_count / n_simulations * 100,
            "percentiles": percentiles,
            "n_simulations": n_simulations,
            "n_trades": n_trades,
            "method": method,
            "initial_capital": self.initial_capital,
        }

    def _calc_max_drawdown(self, equity: np.ndarray) -> float:
        """計算單條權益曲線的最大回撤百分比"""
        cummax = np.maximum.accumulate(equity)
        drawdown = (equity - cummax) / cummax
        return abs(drawdown.min()) * 100

    def _calc_percentiles(self, final_returns: np.ndarray, max_drawdowns: np.ndarray) -> Dict:
        """計算關鍵分位數"""
        # 重排不會改變最終總報酬，所以 final_returns 差異小
        # 但回撤分布會因為路徑不同而顯著不同
        # 用回撤的標準差作為「路徑風險」指標
        dd_std = float(np.std(max_drawdowns))
        dd_mean = float(np.mean(max_drawdowns))
        # 計算「回撤/報酬」比作為風險調整報酬指標
        if dd_mean > 0:
            risk_adj_ratio = float(np.mean(final_returns) / dd_mean)
        else:
            risk_adj_ratio = 0

        return {
            "return_p5": float(np.percentile(final_returns, 5)),
            "return_p25": float(np.percentile(final_returns, 25)),
            "return_p50": float(np.percentile(final_returns, 50)),  # 中位數
            "return_p75": float(np.percentile(final_returns, 75)),
            "return_p95": float(np.percentile(final_returns, 95)),
            "return_mean": float(np.mean(final_returns)),
            "return_std": float(np.std(final_returns)),

            "dd_p5": float(np.percentile(max_drawdowns, 5)),    # 最好情況（最少回撤）
            "dd_p25": float(np.percentile(max_drawdowns, 25)),
            "dd_p50": float(np.percentile(max_drawdowns, 50)),
            "dd_p75": float(np.percentile(max_drawdowns, 75)),
            "dd_p95": float(np.percentile(max_drawdowns, 95)),  # 最壞情況（最深回撤）
            "dd_mean": dd_mean,
            "dd_max": float(np.max(max_drawdowns)),
            "dd_std": dd_std,

            "risk_adj_ratio": risk_adj_ratio,
        }


def format_mc_summary(results: Dict) -> str:
    """產生蒙地卡羅結果摘要文字"""
    if "error" in results:
        return f" 錯誤: {results['error']}"

    p = results["percentiles"]
    s = f"""
=== 蒙地卡羅模擬結果 ({results['n_simulations']} 次, {results['n_trades']} 筆交易) ===

 最終報酬率分布
  - 最壞 5%: {p['return_p5']:+.2f}%
  - 25%:    {p['return_p25']:+.2f}%
  - 中位數: {p['return_p50']:+.2f}%
  - 75%:    {p['return_p75']:+.2f}%
  - 最好 5%: {p['return_p95']:+.2f}%
  - 平均:   {p['return_mean']:+.2f}%
  - 標準差: {p['return_std']:.4f}%

 最大回撤分布
  - 最好 5%: {p['dd_p5']:.2f}%
  - 中位數: {p['dd_p50']:.2f}%
  - 最壞 5%: {p['dd_p95']:.2f}%
  - 平均:   {p['dd_mean']:.2f}%
  - 標準差: {p['dd_std']:.2f}%
  - 最大值: {p['dd_max']:.2f}%

 破產機率: {results['ruin_prob']:.2f}%
 風險調整報酬: {p['risk_adj_ratio']:.2f}
"""
    return s
