"""
combo_STxVolZ.py — 驚喜組合 STxVolZ 的網站回測版。
邏輯：Supertrend 多 + 量異常(VolZ>1) => long；Supertrend 空 + 量異常 => short。
來源：combo_explorer 挖掘到的「趨勢+量確認」低相關組合。
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from strategies.base import Bar, Signal, StrategyBase


class Combo_STxVolZ(StrategyBase):
    name = "combo_STxVolZ"
    description = "Supertrend+量異常確認 (驚喜組合)"
    category = "combo"

    @staticmethod
    def get_params_space() -> dict:
        return {
            "st_period": {"type": "int", "min": 7, "max": 30, "default": 10},
            "st_mult": {"type": "float", "min": 1.0, "max": 4.0, "default": 3.0},
            "vz_window": {"type": "int", "min": 10, "max": 40, "default": 20},
            "vz_th": {"type": "float", "min": 0.5, "max": 3.0, "default": 1.0},
        }

    def init(self, params: dict) -> None:
        self._h: list[float] = []
        self._l: list[float] = []
        self._c: list[float] = []
        self._v: list[float] = []
        self.p = int(params.get("st_period", 10))
        self.m = float(params.get("st_mult", 3.0))
        self.vz_n = int(params.get("vz_window", 20))
        self.vz_th = float(params.get("vz_th", 1.0))
        self._dir = 1  # 當前 Supertrend 方向
        self._prev_up = None
        self._prev_dn = None

    def next(self, bar: Bar):
        self._h.append(bar.high); self._l.append(bar.low)
        self._c.append(bar.close); self._v.append(bar.volume)
        n = len(self._c)
        if n < self.p + 2:
            return None
        # O(1) 增量 Supertrend
        hi = np.array(self._h); lo = np.array(self._l); cl = np.array(self._c)
        atr = (hi[-self.p:] - lo[-self.p:]).mean()  # 簡化 ATR
        mid = (hi[-1] + lo[-1]) / 2
        up = mid - self.m * atr
        dn = mid + self.m * atr
        if self._prev_up is None:
            self._dir = 1
        else:
            if cl[-1] > self._prev_up:
                self._dir = 1
            elif cl[-1] < self._prev_dn:
                self._dir = -1
        self._prev_up = up
        self._prev_dn = dn
        v = np.array(self._v)
        m = v[-self.vz_n:].mean(); sd = v[-self.vz_n:].std()
        z = (v[-1] - m) / (sd + 1e-9)
        if self._dir == 1 and z > self.vz_th:
            return Signal(action="buy", price=bar.close)
        if self._dir == -1 and z > self.vz_th:
            return Signal(action="sell", price=bar.close)
        return Signal(action="close", price=bar.close)
