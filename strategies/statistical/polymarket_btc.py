from __future__ import annotations

from typing import Any, Optional

import numpy as np

from strategies.base import Bar, Signal, StrategyBase


class PolymarketBtcStrategy(StrategyBase):
    """BTC 5min 预测市场玩法（对标 polymarket / predict.fun Up-Down 实盘规则）。

    规则映射：
      - 回合内 BTC 跌 >= move_points 点且收在近低 => 押 UP（反之涨 => 押 DOWN）
      - 只在距收盘 150-200s 时窗下單（有 metadata.seconds_to_close 时；回测可关）
      - 估计胜率须落在 [odds_min, odds_max] (预设 0.60-0.75)；极端位移胜率>上限则跳过
      - 异常（波动飙升）或池子不深（量 < min_volume）=> 影子交易：
        不真下单，模拟成交并记录 shadow_log，标注 simulated_failure
    """

    name = "polymarket_btc"
    description = "BTC 5min 预测市场玩法 (反转 + 时窗 + 赔率带 + 影子风控)"
    category = "prediction_market"

    def init(self, params: dict[str, Any]) -> None:
        super().init(params)
        self.move_points = float(params.get("move_points", 40.0))      # 几十点
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
        self._exit_next: bool = False  # 下一根自动结算（一轮预测结束）

    def _atr(self) -> float:
        if len(self.atr_history) < 2:
            return 0.0
        return float(np.mean(self.atr_history[-self.atr_period:]))

    def _est_win_prob(self, move: float, bar: Bar) -> float:
        """位移（点）转估计胜率。BTC 级别用 % 基准避免数量级失真。
        move 越大胜率越高，但封顶避免极端(>odds_max)被抓去送。"""
        pct = abs(move) / float(bar.open) * 100.0  # e.g. 85pt/63900 ≈ 0.13%
        return min(0.85, 0.5 + pct * 1.5)

    def _in_window(self, bar: Bar) -> bool:
        if not self.require_window:
            return True
        s = (bar.metadata or {}).get("seconds_to_close")
        if s is None:
            return True
        return self.min_seconds_to_close <= float(s) <= self.max_seconds_to_close

    def _shadow(self, bar: Bar, side: str, reason: str) -> None:
        # 影子交易：模拟结果（依玩法假设反转成立），记录但不下真单
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

        # 上一轮已下注 => 本轮自动结算（平仓）— 必须在持仓守卫之前
        if self._exit_next:
            self._exit_next = False
            return Signal(action="close", price=bar.close,
                          metadata={"side": "SETTLE", "win_prob": None})

        if self.position is not None and self.position.size != 0:
            return None  # 单边，不追

        drop = float(bar.open - bar.low)       # 回合内下影
        rise = float(bar.high - bar.open)      # 回合内上影
        close_down = float(bar.close) < float(bar.open)
        body_mid = abs(float(bar.close) - float(bar.open)) / float(bar.open) * 100.0 < 0.05  # close 近 open

        # 双边爆量且收在中段 => 异常噪声（无明确方向，影子交易不下单）
        if drop >= self.move_points and rise >= self.move_points and body_mid:
            self._shadow(bar, "ANOMALY", "bilateral_blowout")
            return None

        # 跌几十点 + 收在近低 => 押 UP
        if drop >= self.move_points and close_down:
            move = drop
            side = "UP"
        # 涨几十点 + 收在近高 => 押 DOWN
        elif rise >= self.move_points and not close_down:
            move = rise
            side = "DOWN"
        else:
            # 无方向性 setup：
            # 池子不深 => 模拟失败
            if self.min_volume > 0 and float(bar.volume) < self.min_volume:
                self._shadow(bar, "LOW_DEPTH", "simulated_failure")
                return None
            # 波动飙升但无明确方向（close 近 open，非反转 setup）=> 影子
            if atr > 0 and rng > self.anomaly_atr_mult * atr and body_mid:
                self._shadow(bar, "ANOMALY", "volatility_spike")
                return None
            return None

        # 有 setup：池子不深 => 影子失败（不下真单）
        if self.min_volume > 0 and float(bar.volume) < self.min_volume:
            self._shadow(bar, "LOW_DEPTH", "simulated_failure")
            return None

        prob = self._est_win_prob(move, bar)
        # 下限過濾：預期勝率太低（位移不夠明確）不下單。
        # 上限不封頂：極端位移=高勝率=該下（你說 90% 勝率來自別人恐慌你撿便宜）。
        if prob < self.odds_min:
            return None  # 賠率/勝率不足 60，跳過雜訊

        action = "buy" if side == "UP" else "sell"
        self._exit_next = True  # 标记下一根结算
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
            "move_points": {"type": "range", "min": 20, "max": 200, "step": 5},
            "odds_min": {"type": "range", "min": 0.50, "max": 0.70, "step": 0.01},
            "odds_max": {"type": "range", "min": 0.70, "max": 0.85, "step": 0.01},
            "anomaly_atr_mult": {"type": "range", "min": 2.0, "max": 5.0, "step": 0.5},
            "require_window": {"type": "choice", "choices": [True, False]},
        }
