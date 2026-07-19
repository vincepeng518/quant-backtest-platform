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
        self._hi: list[float] = []
        self._lo: list[float] = []
        self._cl: list[float] = []
        self._vol: list[float] = []
        self.n = int(params.get("kc_window", 20))
        self.mult = float(params.get("kc_mult", 2.0))
        self.vz_n = int(params.get("vz_window", 20))
        self.vz_th = float(params.get("vz_th", 1.0))

    def _kc(self):
        hi = pd.Series(self._hi); lo = pd.Series(self._lo); cl = pd.Series(self._cl)
        mid = (hi + lo + cl) / 3
        rng = (hi - lo).rolling(self.n).mean()
        upper = mid + self.mult * rng
        lower = mid - self.mult * rng
        return upper, lower

    def _volz(self):
        v = pd.Series(self._vol)
        m = v.rolling(self.vz_n).mean(); sd = v.rolling(self.vz_n).std()
        return (v - m) / sd

    def next(self, bar: Bar):
        self._hi.append(bar.high); self._lo.append(bar.low)
        self._cl.append(bar.close); self._vol.append(bar.volume)
        if len(self._cl) < self.n + 2:
            return None
        upper, lower = self._kc()
        vz = self._volz()
        u = upper.iloc[-2]; l = lower.iloc[-2]; z = vz.iloc[-2]
        c = bar.close
        if c > u and z > self.vz_th:
            return Signal(action="buy", price=bar.close)
        if c < l and z > self.vz_th:
            return Signal(action="sell", price=bar.close)
        return Signal(action="close", price=bar.close)

    def get_params_space(self) -> dict:
        return {
            "kc_window": {"type": "int", "min": 10, "max": 40, "default": 20},
            "kc_mult": {"type": "float", "min": 1.0, "max": 3.0, "default": 2.0},
            "vz_window": {"type": "int", "min": 10, "max": 40, "default": 20},
            "vz_th": {"type": "float", "min": 0.5, "max": 3.0, "default": 1.0},
        }
