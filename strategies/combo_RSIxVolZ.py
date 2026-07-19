"""
combo_RSIxVolZ.py — 驚喜組合 RSIxVolZ 的網站回測版。
邏輯：RSI 超賣 + 量異常 => long；RSI 超買 + 量異常 => short。
來源：combo_explorer 挖掘到的負相關於 BH 組合。
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from strategies.base import Bar, Signal, StrategyBase


class Combo_RSIxVolZ(StrategyBase):
    name = "combo_RSIxVolZ"
    description = "RSI超買超賣+量異常確認 (驚喜組合)"
    category = "combo"

    def init(self, params: dict) -> None:
        self.rw = int(params.get("rsi_window", 14))
        self.ob = int(params.get("rsi_ob", 70))
        self.os = int(params.get("rsi_os", 30))
        self.vz_n = int(params.get("vz_window", 20))
        self.vz_th = float(params.get("vz_th", 1.0))
        cap = 100000
        self._c = np.empty(cap); self._v = np.empty(cap)
        self._i = 0

    def next(self, bar: Bar):
        i = self._i
        self._c[i] = bar.close; self._v[i] = bar.volume
        self._i += 1
        n = self._i
        if n < max(self.rw, self.vz_n) + 2:
            return None
        cl = self._c[:n]; v = self._v[:n]
        d = np.diff(cl[-(self.rw + 1):])
        gain = d[d > 0].mean() if np.any(d > 0) else 0.0
        loss = -d[d < 0].mean() if np.any(d < 0) else 0.0
        rs = gain / (loss + 1e-9)
        rsi = 100 - 100 / (1 + rs)
        m = v[-self.vz_n:].mean(); sd = v[-self.vz_n:].std()
        z = (v[-1] - m) / (sd + 1e-9)
        c = bar.close
        if rsi < self.os and z > self.vz_th:
            return Signal(action="buy", price=bar.close)
        if rsi > self.ob and z > self.vz_th:
            return Signal(action="sell", price=bar.close)
        return Signal(action="close", price=bar.close)

    @staticmethod
    def get_params_space() -> dict:
        return {
            "rsi_window": {"type": "int", "min": 5, "max": 30, "default": 14},
            "rsi_ob": {"type": "int", "min": 60, "max": 80, "default": 70},
            "rsi_os": {"type": "int", "min": 20, "max": 40, "default": 30},
            "vz_window": {"type": "int", "min": 10, "max": 40, "default": 20},
            "vz_th": {"type": "float", "min": 0.5, "max": 3.0, "default": 1.0},
        }
