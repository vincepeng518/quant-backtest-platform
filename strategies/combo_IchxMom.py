"""
combo_IchxMom.py — 驚喜組合 IchxMom 的網站回測版。
邏輯：價在 Ichimoku 雲上 + 動量為正 => long；雲下 + 動量為負 => short。
來源：combo_explorer 挖掘到負相關於 BH (-0.37) 的組合。
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from strategies.base import Bar, Signal, StrategyBase


class Combo_IchxMom(StrategyBase):
    name = "combo_IchxMom"
    description = "Ichimoku雲+動量 (驚喜組合)"
    category = "combo"

    @staticmethod
    def get_params_space() -> dict:
        return {
            "tenkan": {"type": "int", "min": 7, "max": 20, "default": 9},
            "kijun": {"type": "int", "min": 20, "max": 40, "default": 26},
            "senkou": {"type": "int", "min": 40, "max": 80, "default": 52},
            "mom_window": {"type": "int", "min": 3, "max": 20, "default": 5},
        }

    def init(self, params: dict) -> None:
        self._h: list[float] = []
        self._l: list[float] = []
        self._c: list[float] = []
        self.ten = int(params.get("tenkan", 9))
        self.kij = int(params.get("kijun", 26))
        self.sen = int(params.get("senkou", 52))
        self.mom_w = int(params.get("mom_window", 5))

    def _ichimoku(self):
        h = pd.Series(self._h); l = pd.Series(self._l); c = pd.Series(self._c)
        tenk = (h.rolling(self.ten).max() + h.rolling(self.ten).min()) / 2
        kij = (h.rolling(self.kij).max() + h.rolling(self.kij).min()) / 2
        senk = (h.rolling(self.sen).max() + h.rolling(self.sen).min()) / 2
        return (tenk + senk) / 2

    def next(self, bar: Bar):
        self._h.append(bar.high); self._l.append(bar.low); self._c.append(bar.close)
        n = len(self._c)
        if n < self.sen + 2:
            return None
        # O(1) 增量
        hi = np.array(self._h); lo = np.array(self._l)
        tenk = (hi[-self.ten:].max() + lo[-self.ten:].min()) / 2
        senk = (hi[-self.sen:].max() + lo[-self.sen:].min()) / 2
        spanA = (tenk + senk) / 2
        c = bar.close
        mom = self._c[-1] / self._c[-1 - self.mom_w] - 1 if n > self.mom_w else 0
        if c > spanA and mom > 0:
            return Signal(action="buy", price=bar.close)
        if c < spanA and mom < 0:
            return Signal(action="sell", price=bar.close)
        return Signal(action="close", price=bar.close)
