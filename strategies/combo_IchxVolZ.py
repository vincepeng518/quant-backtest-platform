"""
combo_IchxVolZ.py — 驚喜組合 IchxVolZ 的網站回測版。
邏輯：價格在 Ichimoku 雲上 + 量異常(VolZ>1.5) => long；
    價格在雲下 + 量異常 => short。
來源：combo_explorer 挖掘到的負相關於 BH 的組合。
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from strategies.base import Bar, Signal, StrategyBase


class Combo_IchxVolZ(StrategyBase):
    name = "combo_IchxVolZ"
    description = "Ichimoku雲+量異常確認 (驚喜組合)"
    category = "combo"

    def init(self, params: dict) -> None:
        self.ten = int(params.get("tenkan", 9))
        self.kij = int(params.get("kijun", 26))
        self.sen = int(params.get("senkou", 52))
        self.vz_n = int(params.get("vz_window", 20))
        self.vz_th = float(params.get("vz_th", 1.5))
        # 預分配 numpy 陣列 (增量 append O(1), 不每次重建 list→array)
        cap = 100000
        self._h = np.empty(cap); self._l = np.empty(cap)
        self._c = np.empty(cap); self._v = np.empty(cap)
        self._i = 0

    def next(self, bar: Bar):
        i = self._i
        self._h[i] = bar.high; self._l[i] = bar.low
        self._c[i] = bar.close; self._v[i] = bar.volume
        self._i += 1
        n = self._i
        if n < self.sen + 2:
            return None
        # O(1) 切片 (視圖, 不複製整條)
        hi = self._h[:n]; lo = self._l[:n]; v = self._v[:n]
        tenk = (hi[-self.ten:].max() + lo[-self.ten:].min()) / 2
        senk = (hi[-self.sen:].max() + lo[-self.sen:].min()) / 2
        spanA = (tenk + senk) / 2
        m = v[-self.vz_n:].mean(); sd = v[-self.vz_n:].std()
        z = (v[-1] - m) / (sd + 1e-9)
        c = bar.close
        if c > spanA and z > self.vz_th:
            return Signal(action="buy", price=bar.close)
        if c < spanA and z > self.vz_th:
            return Signal(action="sell", price=bar.close)
        return Signal(action="close", price=bar.close)

    @staticmethod
    def get_params_space() -> dict:
        return {
            "tenkan": {"type": "int", "min": 7, "max": 20, "default": 9},
            "kijun": {"type": "int", "min": 20, "max": 40, "default": 26},
            "senkou": {"type": "int", "min": 40, "max": 80, "default": 52},
            "vz_window": {"type": "int", "min": 10, "max": 40, "default": 20},
            "vz_th": {"type": "float", "min": 0.5, "max": 3.0, "default": 1.5},
        }
