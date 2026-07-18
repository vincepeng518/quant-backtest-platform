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

    def __init__(self) -> None:
        super().__init__()
        self._hi: list[float] = []
        self._lo: list[float] = []
        self._cl: list[float] = []
        self._vol: list[float] = []

    def _kc(self, n=20, mult=2):
        hi = pd.Series(self._hi); lo = pd.Series(self._lo); cl = pd.Series(self._cl)
        mid = (hi + lo + cl) / 3
        rng = (hi - lo).rolling(n).mean()
        upper = mid + mult * rng
        lower = mid - mult * rng
        return upper, lower

    def _volz(self, n=20):
        v = pd.Series(self._vol)
        m = v.rolling(n).mean(); sd = v.rolling(n).std()
        return (v - m) / sd

    def next(self, bar: Bar) -> Signal | None:
        self._hi.append(bar.high); self._lo.append(bar.low)
        self._cl.append(bar.close); self._vol.append(bar.volume)
        L = len(self._cl)
        if L < 22:
            return None
        upper, lower = self._kc()
        vz = self._volz()
        u = upper.iloc[-2]; l = lower.iloc[-2]; z = vz.iloc[-2]
        c = bar.close
        if c > u and z > 1:
            return Signal(action="buy", price=bar.close)
        if c < l and z > 1:
            return Signal(action="sell", price=bar.close)
        return Signal(action="close", price=bar.close)
