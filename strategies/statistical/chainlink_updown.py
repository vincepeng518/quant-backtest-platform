from __future__ import annotations

from typing import Any, Optional

import numpy as np

from strategies.base import Bar, Signal, StrategyBase


class ChainlinkUpDownStrategy(StrategyBase):
    """Chainlink Up/Down 價格市場策略（對標 predict.fun BTC/USDT 等週期市場）。

    每根 bar 預測下一輪價格相對本輪是 Up 還 Down：
      - action="buy"  => 押 Up (YES)
      - action="sell" => 押 Down (NO)
      - action="close" => 平倉換邊
    兩種模式：
      - momentum   : 近 N 根報酬突破閾值 => 順勢
      - reversion  : RSI 極值 => 均值回歸反手
    純單源價格策略，直接複用現有回測引擎。
    """

    name = "chainlink_updown"
    description = "Chainlink Up/Down 價格市場策略 (predict.fun 風格)"
    category = "prediction_market"

    def init(self, params: dict[str, Any]) -> None:
        super().init(params)
        self.mode = str(params.get("mode", "momentum"))  # momentum | reversion
        self.lookback = int(params.get("lookback", 14))
        self.threshold = float(params.get("threshold", 0.002))  # 動量模式報酬閾值
        self.rsi_period = int(params.get("rsi_period", 14))
        self.rsi_overbought = float(params.get("rsi_overbought", 70))
        self.rsi_oversold = float(params.get("rsi_oversold", 30))
        self.prices: list[float] = []

    def _rsi(self) -> float:
        arr = np.asarray(self.prices[-(self.rsi_period + 1):], dtype=float)
        if len(arr) < self.rsi_period + 1:
            return 50.0
        deltas = np.diff(arr)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        avg_gain = gains.mean()
        avg_loss = losses.mean()
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return float(100 - 100 / (1 + rs))

    def next(self, bar: Bar) -> Optional[Signal]:
        self.prices.append(float(bar.close))
        if len(self.prices) < self.lookback + 1:
            return None

        if self.mode == "momentum":
            window = np.asarray(self.prices[-self.lookback:], dtype=float)
            ret = float(window[-1] / window[0] - 1)
            if ret > self.threshold and (self.position is None or self.position.size == 0):
                return Signal(action="buy", price=bar.close, metadata={"side": "UP", "ret": ret})
            if ret < -self.threshold and (self.position is None or self.position.size == 0):
                return Signal(action="sell", price=bar.close, metadata={"side": "DOWN", "ret": ret})
            # 反轉平倉換邊
            if self.position is not None and self.position.size != 0:
                if (self.position.size > 0 and ret < -self.threshold) or (
                    self.position.size < 0 and ret > self.threshold
                ):
                    return Signal(action="close", metadata={"side": "FLIP", "ret": ret})
            return None

        # reversion mode
        rsi = self._rsi()
        if rsi >= self.rsi_overbought and (self.position is None or self.position.size == 0):
            return Signal(action="sell", price=bar.close, metadata={"side": "DOWN", "rsi": rsi})
        if rsi <= self.rsi_oversold and (self.position is None or self.position.size == 0):
            return Signal(action="buy", price=bar.close, metadata={"side": "UP", "rsi": rsi})
        if self.position is not None and self.position.size != 0:
            # 回到中性區平倉
            if self.rsi_oversold < rsi < self.rsi_overbought:
                return Signal(action="close", metadata={"side": "NEUTRAL", "rsi": rsi})
        return None

    def warmup_period(self) -> int:
        return max(self.lookback, self.rsi_period) + 1

    def get_params(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "lookback": self.lookback,
            "threshold": self.threshold,
            "rsi_period": self.rsi_period,
            "rsi_overbought": self.rsi_overbought,
            "rsi_oversold": self.rsi_oversold,
        }

    def get_params_space(self) -> dict[str, Any]:
        return {
            "mode": {"type": "choice", "choices": ["momentum", "reversion"]},
            "lookback": {"type": "range", "min": 5, "max": 50, "step": 1},
            "threshold": {"type": "range", "min": 0.001, "max": 0.02, "step": 0.001},
            "rsi_period": {"type": "range", "min": 7, "max": 30, "step": 1},
        }
