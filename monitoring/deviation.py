from __future__ import annotations

import statistics
from typing import Optional


class DeviationCalculator:
    """Phase 1: 現價 vs 目標價偏離計算 + 動態閾值。

    將「現價低於目標價 19~37 美元」量化為動態閾值。
    - target 給定時：dev = spot - target（有明確目標價，如 Chainlink feed）。
    - target=None 時：用近期現價移動均值當基線，dev = spot - mean（自適應）。
    - 動態閾值：base ± 近期偏離波動，平穩盤收緊、劇烈盤放寬。
    """

    def __init__(
        self,
        base_points: float = 25.0,
        min_points: float = 15.0,
        max_points: float = 80.0,
        vol_mult: float = 1.5,
        window: int = 60,
    ) -> None:
        self.base_points = base_points
        self.min_points = min_points
        self.max_points = max_points
        self.vol_mult = vol_mult
        self.window = window
        self._prices: list[float] = []
        self._devs: list[float] = []

    def _push(self, price: float) -> None:
        self._prices.append(price)
        if len(self._prices) > self.window:
            self._prices.pop(0)

    def dynamic_threshold(self) -> float:
        if len(self._devs) < 5:
            return self.base_points
        std = statistics.pstdev(self._devs)
        thr = self.base_points + self.vol_mult * std
        return min(self.max_points, max(self.min_points, thr))

    def evaluate(self, spot: float, target: Optional[float] = None) -> dict:
        if target is not None:
            dev = spot - target
            self._push(spot)
            self._devs.append(dev)
            if len(self._devs) > self.window:
                self._devs.pop(0)
            thr = self.dynamic_threshold()
        else:
            if len(self._prices) < 5:
                # 基線尚未建立：先記錄價格，不觸發
                self._push(spot)
                return {"deviation": 0.0, "threshold": self.base_points,
                        "triggered": False, "direction": None}
            # 基線 = 當前價之前的移動均值 (不含本筆)
            baseline = sum(self._prices) / len(self._prices)
            dev = spot - baseline
            # 先算閾值 (用歷史偏離, 不含當前筆, 避免當前暴跌自己拉高閾值)
            thr = self.dynamic_threshold()
            self._push(spot)
            self._devs.append(dev)
            if len(self._devs) > self.window:
                self._devs.pop(0)
        triggered = abs(dev) >= thr
        # 描述性方向：價格相對基線偏低/偏高（非下注方向）
        direction = "BELOW" if dev < 0 else "ABOVE"
        return {
            "deviation": round(dev, 2),
            "threshold": round(thr, 2),
            "triggered": triggered,
            "direction": direction if triggered else None,
        }
