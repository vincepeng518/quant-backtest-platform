from __future__ import annotations

from typing import Any, Optional

import numpy as np

from strategies.base import Bar, Signal, StrategyBase


class PolymarketBtcStrategy(StrategyBase):
    """BTC 5min 预测市场玩法（对标 polymarket / predict.fun Up-Down 实盘规则）。

    玩法核心（2026-07-13 实盘经验）：
      - 在轮次(5min)内 BTC 出现“恐慌性”下跌 => 收尾(150-200s 窗口)会被拉回 => 买 UP
      - 反之亦然。胜率(熟练后)声称 ~90%，来自赔付结构 + 情绪极端反转的 micro-structure
    数据要求（需 data/round_builder 注入 metadata）：
      - metadata.round_open: 轮次开盘价
      - metadata.seconds_to_close: 当前 1m 棒距轮次收盘剩余秒数
      - metadata.drop_from_open_pct: 从 round_open 到本根 close 的累计跌幅(%)
      - metadata.rsi: 轮次序列 RSI(14)
    风控：
      - 异常（双边爆量 / 波动飙升且无方向）=> 影子交易（不下真单，记录 shadow_log）
      - 池子不深（量 < min_volume）=> 影子交易标 simulated_failure
    结算：每轮下注后下一根自动平仓（一轮预测结束）。
    """

    name = "polymarket_btc"
    description = "BTC 5min 预测市场玩法 (情绪极端反转 + 150-200s 时窗 + 影子风控)"
    category = "prediction_market"

    def init(self, params: dict[str, Any]) -> None:
        super().init(params)
        self.drop_pct = float(params.get("drop_pct", 1.5))          # 轮内累计跌幅% 阈值（恐慌）
        self.rsi_max = float(params.get("rsi_max", 30.0))           # RSI 上限（超卖）
        self.min_seconds_to_close = int(params.get("min_seconds_to_close", 150))
        self.max_seconds_to_close = int(params.get("max_seconds_to_close", 200))
        self.require_window = bool(params.get("require_window", True))
        self.anomaly_atr_mult = float(params.get("anomaly_atr_mult", 3.0))
        self.min_volume = float(params.get("min_volume", 0.0))
        self.atr_period = int(params.get("atr_period", 20))
        self.atr_history: list[float] = []
        self.shadow_log: list[dict] = []
        self._exit_next: bool = False

    def _atr(self) -> float:
        if len(self.atr_history) < 2:
            return 0.0
        return float(np.mean(self.atr_history[-self.atr_period:]))

    def _in_window(self, bar: Bar) -> bool:
        if not self.require_window:
            return True
        s = (bar.metadata or {}).get("seconds_to_close")
        if s is None:
            return True  # 无 metadata 时退化为全时段（兼容旧回测）
        return self.min_seconds_to_close <= float(s) <= self.max_seconds_to_close

    def _shadow(self, bar: Bar, side: str, reason: str) -> None:
        self.shadow_log.append({
            "timestamp": str(bar.timestamp),
            "side": side,
            "reason": reason,
            "simulated_fill": True,
            "recorded": True,
        })

    def next(self, bar: Bar) -> Optional[Signal]:
        rng = float(bar.high - bar.low)
        self.atr_history.append(rng)
        atr = self._atr()

        # 上一轮已下注 => 本轮自动结算（最高优先级，绕过时窗/风控）
        if self._exit_next:
            self._exit_next = False
            return Signal(action="close", price=bar.close,
                          metadata={"side": "SETTLE", "win_prob": None})

        if not self._in_window(bar):
            return None

        if self.position is not None and self.position.size != 0:
            return None  # 单边，不追

        # 池子不深 => 任何下注都改为影子交易（模拟失败），优先于信号判定
        if self.min_volume > 0 and float(bar.volume) < self.min_volume:
            self._shadow(bar, "LOW_DEPTH", "simulated_failure")
            return None

        meta = bar.metadata or {}
        round_open = meta.get("round_open")
        drop_pct = meta.get("drop_from_open_pct")
        rsi = meta.get("rsi")
        body_mid = abs(float(bar.close) - float(bar.open)) / float(bar.open) * 100.0 < 0.05

        # 双边爆量且收在中段 => 异常噪声（无明确方向）
        drop = float(bar.open - bar.low)
        rise = float(bar.high - bar.open)
        if drop >= self.atr_period and rise >= self.atr_period and body_mid:
            self._shadow(bar, "ANOMALY", "bilateral_blowout")
            return None

        # 情绪极端反转判定：
        # 恐慌 => 轮内从 round_open 跌幅 >= drop_pct 且 RSI 超卖 => 押 UP（收尾拉回）
        if round_open is not None and drop_pct is not None:
            panic = float(drop_pct) >= self.drop_pct and (rsi is None or float(rsi) <= self.rsi_max)
            euphoria = float(drop_pct) <= -self.drop_pct and (rsi is None or float(rsi) >= (100 - self.rsi_max))
            if panic:
                self._exit_next = True
                return Signal(action="buy", price=bar.close,
                              metadata={"side": "UP", "drop_pct": round(float(drop_pct), 2),
                                        "rsi": rsi, "win_prob": None})
            if euphoria:
                self._exit_next = True
                return Signal(action="sell", price=bar.close,
                              metadata={"side": "DOWN", "rise_pct": round(-float(drop_pct), 2),
                                        "rsi": rsi, "win_prob": None})

        # 无方向性 setup：波动飙升但无明确方向（close 近 open）=> 影子
        if atr > 0 and rng > self.anomaly_atr_mult * atr and body_mid:
            self._shadow(bar, "ANOMALY", "volatility_spike")
            return None
        return None

    def warmup_period(self) -> int:
        return max(self.atr_period, self.atr_period) + 1

    def get_params(self) -> dict[str, Any]:
        return {
            "drop_pct": self.drop_pct,
            "rsi_max": self.rsi_max,
            "min_seconds_to_close": self.min_seconds_to_close,
            "max_seconds_to_close": self.max_seconds_to_close,
            "require_window": self.require_window,
            "anomaly_atr_mult": self.anomaly_atr_mult,
            "min_volume": self.min_volume,
        }

    def get_params_space(self) -> dict[str, Any]:
        return {
            "drop_pct": {"type": "range", "min": 0.5, "max": 4.0, "step": 0.1},
            "rsi_max": {"type": "range", "min": 20.0, "max": 40.0, "step": 1.0},
            "min_seconds_to_close": {"type": "range", "min": 120, "max": 180, "step": 10},
            "max_seconds_to_close": {"type": "range", "min": 180, "max": 220, "step": 10},
            "anomaly_atr_mult": {"type": "range", "min": 2.0, "max": 5.0, "step": 0.5},
            "require_window": {"type": "choice", "choices": [True, False]},
        }
