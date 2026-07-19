"""
combo_KCxVolZ.py — 驚喜組合 KCxVolZ 的網站回測版。
邏輯：KC(Keltner) 上軌突破 + 量異常(VolZ>1) => long；
     KC 下軌跌破 + 量異常 => short。
來源：combo_explorer 挖掘到的低 BH 相關、可控回撤組合。
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from strategies.base import Bar, Signal, StrategyBase


class Combo_KCxVolZ(StrategyBase):
    name = "combo_KCxVolZ"
    description = "KC突破+量異常確認 (驚喜組合)"
    category = "combo"

    def init(self, params: dict) -> None:
        self.n = int(params.get("kc_window", 20))
        self.mult = float(params.get("kc_mult", 2.0))
        self.vz_n = int(params.get("vz_window", 20))
        self.vz_th = float(params.get("vz_th", 1.0))
        cap = 100000
        self._hi = np.empty(cap); self._lo = np.empty(cap)
        self._cl = np.empty(cap); self._vol = np.empty(cap)
        self._i = 0

    def next(self, bar: Bar):
        i = self._i
        self._hi[i] = bar.high; self._lo[i] = bar.low
        self._cl[i] = bar.close; self._vol[i] = bar.volume
        self._i += 1
        n = self._i
        if n < self.n + 2:
            return None
        hi = self._hi[:n]; lo = self._lo[:n]; cl = self._cl[:n]
        hlc3 = (hi[-self.n:] + lo[-self.n:] + cl[-self.n:]) / 3.0
        mid = hlc3.mean()
        rng = (hi[-self.n:] - lo[-self.n:]).mean()
        u = mid + self.mult * rng
        l = mid - self.mult * rng
        v = self._vol[:n]
        m = v[-self.vz_n:].mean(); sd = v[-self.vz_n:].std()
        z = (v[-1] - m) / (sd + 1e-9)
        c = bar.close
        if c > u and z > self.vz_th:
            return Signal(action="buy", price=bar.close)
        if c < l and z > self.vz_th:
            return Signal(action="sell", price=bar.close)
        return Signal(action="close", price=bar.close)

    @staticmethod
    def get_params_space() -> dict:
        return {
            "kc_window": {"type": "int", "min": 10, "max": 40, "default": 20},
            "kc_mult": {"type": "float", "min": 1.0, "max": 3.0, "default": 2.0},
            "vz_window": {"type": "int", "min": 10, "max": 40, "default": 20},
            "vz_th": {"type": "float", "min": 0.5, "max": 3.0, "default": 1.0},
        }
