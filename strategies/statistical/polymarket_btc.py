from __future__ import annotations

from typing import Any, Optional

import numpy as np

from strategies.base import Bar, Signal, StrategyBase


class PolymarketBtcStrategy(StrategyBase):
    """BTC 5min 預測市場玩法（對標 polymarket / predict.fun Up-Down 實盤規則）。

    規則映射：
      - 回合內 BTC 跌 >= move_points 點且收在近低 => 押 UP（反之漲 => 押 DOWN）
      - 只在距收盤 150-200s 時窗下單（有 metadata.seconds_to_close 時；回測可關）
      - 估計勝率須落在 [odds_min, odds_max] (預設 0.60-0.75)；極端位移勝率>上限則跳過
      - 異常（波動超 ATR 倍數）或池子不深（量 < min_volume）=> 影子交易：
        不真下單，模擬成交並記入 shadow_log，標注 simulated_failure
    """

    name = "polymarket_btc"
    description = "BTC 5min 預測市場玩法 (反轉 + 時窗 + 賠率帶 + 影子風控)"
    category = "prediction_market"

    def init(self, params: dict[str, Any]) -> None:
        super().init(params)
        self.move_points = float(params.get("move_points", 40.0))      # 幾十點
        self.round_seconds = int(params.get("round_seconds", 300))
        self.min_seconds_to_close = int(params.get("min_seconds_to_close", 150))
        self.max_seconds_to_close = int(params.get("max_seconds_to_close", 200))
        self.require_window = bool(params.get("require_window", False))
        self.odds_min = float(params.get("odds_min", 0.60))
        self.odds_max = float(params.get("odds_max", 0.75))
        self.anomaly_atr_mult = float(params.get("anomaly_atr_mult", 3.0))
        self.min_volume = float(params.get("min_volume", 0.0))         # 池深代理
        self.atr_period = int(params.get("atr_period", 20))
        self.atr_history: list[float] = []
        self.shadow_log: list[dict] = []

    def _atr(self) -> float:
        if len(self.atr_history) < 2:
            return 0.0
        return float(np.mean(self.atr_history[-self.atr_period:]))

    def _est_win_prob(self, move: float) -> float:
        """位移越大勝率越高，但封頂避免極端(>odds_max)被抓去送。"""
        return min(0.85, 0.5 + abs(move) / 200.0)

    def _in_window(self, bar: Bar) -> bool:
        if not self.require_window:
            return True
        s = (bar.metadata or {}).get("seconds_to_close")
        if s is None:
            return True
        return self.min_seconds_to_close <= float(s) <= self.max_seconds_to_close

    def _shadow(self, bar: Bar, side: str, reason: str) -> None:
        # 影子交易：模擬結果（依玩法假設反轉成立），記錄但不下真單
        self.shadow_log.append({
            "timestamp": str(bar.timestamp),
            "side": side,
            "reason": reason,
            "simulated_fill": True,
            "recorded": True,
        })

    def next(self, bar: Bar) -> Optional[Signal]:
        # 更新 ATR（用 bar range 代理）
        rng = float(bar.high - bar.low)
        self.atr_history.append(rng)
        atr = self._atr()

        if not self._in_window(bar):
            return None
        if self.position is not None and self.position.size != 0:
            return None  # 單邊，不追

        drop = float(bar.open - bar.low)       # 回合內下影
        rise = float(bar.high - bar.open)      # 回合內上影
        close_down = float(bar.close) < float(bar.open)

        # 跌幾十點 + 收在近低 => 押 UP
        if drop >= self.move_points and close_down:
            move = drop
            side = "UP"
        # 漲幾十點 + 收在近高 => 押 DOWN
        elif rise >= self.move_points and not close_down:
            move = rise
            side = "DOWN"
        else:
            # 無方向性 setup：進異常/池深風控（影子交易）
            if self.min_volume > 0 and float(bar.volume) < self.min_volume:
                self._shadow(bar, "LOW_DEPTH", "simulated_failure")
                return None
            if atr > 0 and rng > self.anomaly_atr_mult * atr:
                self._shadow(bar, "ANOMALY", "volatility_spike")
                return None
            return None

        # 雙邊爆量（上下影都超閾值）=> 異常，影子交易不下單
        if drop >= self.move_points and rise >= self.move_points:
            self._shadow(bar, "ANOMALY", "bilateral_blowout")
            return None

        # 有 setup：池子不深 => 影子失敗（不下真單）
        if self.min_volume > 0 and float(bar.volume) < self.min_volume:
            self._shadow(bar, "LOW_DEPTH", "simulated_failure")
            return None

        prob = self._est_win_prob(move)
        if not (self.odds_min <= prob <= self.odds_max):
            return None  # 賠率不在 60-75 帶：極端位移易吐光，跳過

        action = "buy" if side == "UP" else "sell"
        return Signal(action=action, price=bar.close,
                      metadata={"side": side, "win_prob": round(prob, 3),
                                "move_points": round(move, 1)})

    def warmup_period(self) -> int:
        return self.atr_period + 1

    def get_params(self) -> dict[str, Any]:
        return {
            "move_points": self.move_points,
            "min_seconds_to_close": self.min_seconds_to_close,
            "max_seconds_to_close": self.max_seconds_to_close,
            "require_window": self.require_window,
            "odds_min": self.odds_min,
            "odds_max": self.odds_max,
            "anomaly_atr_mult": self.anomaly_atr_mult,
            "min_volume": self.min_volume,
        }

    def get_params_space(self) -> dict[str, Any]:
        return {
            "move_points": {"type": "range", "min": 20, "max": 100, "step": 5},
            "odds_min": {"type": "range", "min": 0.50, "max": 0.70, "step": 0.01},
            "odds_max": {"type": "range", "min": 0.70, "max": 0.85, "step": 0.01},
            "anomaly_atr_mult": {"type": "range", "min": 2.0, "max": 5.0, "step": 0.5},
            "require_window": {"type": "choice", "choices": [True, False]},
        }
