"""
combo_IchxMom.py — 驚喜組合 IchxMom 的網站回測版。
邏輯：價格在 Ichimoku 雲上 + 動量>0 => long；雲下 + 動量<0 => short。
來源：combo_explorer 挖掘到的負相關於 BH 組合。
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from strategies.base import Bar, Signal, StrategyBase


class Combo_IchxMom(StrategyBase):
    name = "combo_IchxMom"
    description = "Ichimoku雲+動量確認 (驚喜組合)"
    category = "combo"

    def init(self, params: dict) -> None:
        self.ten = int(params.get("tenkan", 9))
        self.kij = int(params.get("kijun", 26))
        self.sen = int(params.get("senkou", 52))
        self.mom_w = int(params.get("mom_window", 5))
        cap = 100000
        self._h = np.empty(cap); self._l = np.empty(cap); self._c = np.empty(cap)
        self._i = 0

    def next(self, bar: Bar):
        i = self._i
        self._h[i] = bar.high; self._l[i] = bar.low; self._c[i] = bar.close
        self._i += 1
        n = self._i
        if n < self.sen + 2:
            return None
        hi = self._h[:n]; lo = self._l[:n]
        tenk = (hi[-self.ten:].max() + lo[-self.ten:].min()) / 2
        senk = (hi[-self.sen:].max() + lo[-self.sen:].min()) / 2
        spanA = (tenk + senk) / 2
        c = bar.close
        mom = self._c[n - 1] / self._c[n - 1 - self.mom_w] - 1 if n > self.mom_w else 0
        if c > spanA and mom > 0:
            return Signal(action="buy", price=bar.close)
        if c < spanA and mom < 0:
            return Signal(action="sell", price=bar.close)
        return Signal(action="close", price=bar.close)

    @staticmethod
    def get_params_space() -> dict:
        return {
            "tenkan": {"type": "int", "min": 7, "max": 20, "default": 9},
            "kijun": {"type": "int", "min": 20, "max": 40, "default": 26},
            "senkou": {"type": "int", "min": 40, "max": 80, "default": 52},
            "mom_window": {"type": "int", "min": 3, "max": 20, "default": 5},
        }
