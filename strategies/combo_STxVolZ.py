"""
combo_STxVolZ.py — 驚喜組合 STxVolZ 的網站回測版。
邏輯：Supertrend 方向 + 量異常 => long/short。
來源：combo_explorer 挖掘到的負相關於 BH 組合。
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from strategies.base import Bar, Signal, StrategyBase


class Combo_STxVolZ(StrategyBase):
    name = "combo_STxVolZ"
    description = "Supertrend+量異常確認 (驚喜組合)"
    category = "combo"

    def init(self, params: dict) -> None:
        self.p = int(params.get("st_period", 10))
        self.m = float(params.get("st_mult", 3.0))
        self.vz_n = int(params.get("vz_window", 20))
        self.vz_th = float(params.get("vz_th", 1.0))
        cap = 100000
        self._h = np.empty(cap); self._l = np.empty(cap)
        self._c = np.empty(cap); self._v = np.empty(cap)
        self._i = 0
        self._dir = 1
        self._prev_up = None
        self._prev_dn = None

    def next(self, bar: Bar):
        i = self._i
        self._h[i] = bar.high; self._l[i] = bar.low
        self._c[i] = bar.close; self._v[i] = bar.volume
        self._i += 1
        n = self._i
        if n < self.p + 2:
            return None
        hi = self._h[:n]; lo = self._l[:n]; cl = self._c[:n]
        atr = (hi[-self.p:] - lo[-self.p:]).mean()
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
        v = self._v[:n]
        m = v[-self.vz_n:].mean(); sd = v[-self.vz_n:].std()
        z = (v[-1] - m) / (sd + 1e-9)
        if self._dir == 1 and z > self.vz_th:
            return Signal(action="buy", price=bar.close)
        if self._dir == -1 and z > self.vz_th:
            return Signal(action="sell", price=bar.close)
        return Signal(action="close", price=bar.close)

    @staticmethod
    def get_params_space() -> dict:
        return {
            "st_period": {"type": "int", "min": 5, "max": 30, "default": 10},
            "st_mult": {"type": "float", "min": 1.0, "max": 5.0, "default": 3.0},
            "vz_window": {"type": "int", "min": 10, "max": 40, "default": 20},
            "vz_th": {"type": "float", "min": 0.5, "max": 3.0, "default": 1.0},
        }
