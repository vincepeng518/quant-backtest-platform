"""
combo_RSIxVolZ.py — 驚喜組合 RSIxVolZ 的網站回測版。
邏輯：RSI 超賣(<30) + 量異常(VolZ>1) => long；RSI 超買(>70) + 量異常 => short。
來源：combo_explorer 挖掘到的「超買超賣+量確認」低相關組合。
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from strategies.base import Bar, Signal, StrategyBase


class Combo_RSIxVolZ(StrategyBase):
    name = "combo_RSIxVolZ"
    description = "RSI超買超賣+量異常確認 (驚喜組合)"
    category = "combo"

    @staticmethod
    def get_params_space() -> dict:
        return {
            "rsi_window": {"type": "int", "min": 7, "max": 30, "default": 14},
            "rsi_ob": {"type": "int", "min": 60, "max": 85, "default": 70},
            "rsi_os": {"type": "int", "min": 15, "max": 40, "default": 30},
            "vz_window": {"type": "int", "min": 10, "max": 40, "default": 20},
            "vz_th": {"type": "float", "min": 0.5, "max": 3.0, "default": 1.0},
        }

    def init(self, params: dict) -> None:
        self._c: list[float] = []
        self._v: list[float] = []
        self.rw = int(params.get("rsi_window", 14))
        self.ob = int(params.get("rsi_ob", 70))
        self.os = int(params.get("rsi_os", 30))
        self.vz_n = int(params.get("vz_window", 20))
        self.vz_th = float(params.get("vz_th", 1.0))

    def _rsi(self):
        c = pd.Series(self._c)
        d = c.diff()
        up = d.clip(lower=0).rolling(self.rw).mean()
        dn = (-d.clip(upper=0)).rolling(self.rw).mean()
        rs = up / (dn + 1e-9)
        return 100 - 100 / (1 + rs)

    def _volz(self):
        v = pd.Series(self._v)
        m = v.rolling(self.vz_n).mean(); sd = v.rolling(self.vz_n).std()
        return (v - m) / sd

    def next(self, bar: Bar):
        self._c.append(bar.close); self._v.append(bar.volume)
        if len(self._c) < max(self.rw, self.vz_n) + 2:
            return None
        r = self._rsi(); z = self._volz()
        rsi = r.iloc[-2]; zz = z.iloc[-2]; c = bar.close
        if rsi < self.os and zz > self.vz_th:
            return Signal(action="buy", price=bar.close)
        if rsi > self.ob and zz > self.vz_th:
            return Signal(action="sell", price=bar.close)
        return Signal(action="close", price=bar.close)
