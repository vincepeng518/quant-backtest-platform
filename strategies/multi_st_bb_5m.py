"""
multi_st_bb_5m.py — Multi-Supertrend + Bollinger Squeeze for 5m BTC direction prediction.
Runs on 1m data, generates signal every 5 bars for next 5m direction.
Incremental O(1) per bar — fast enough for 5000+ bar backtests.
"""
from __future__ import annotations
import numpy as np
from strategies.base import Bar, Signal, StrategyBase


class MultiST_BB_5m(StrategyBase):
    name = "multi_st_bb_5m"
    description = "Multi-Supertrend + BB Squeeze 預測 5m BTC 方向"
    category = "ml_prediction"

    def init(self, params: dict) -> None:
        self.atr_p1 = int(params.get("atr_p1", 10))
        self.atr_p2 = int(params.get("atr_p2", 11))
        self.atr_p3 = int(params.get("atr_p3", 12))
        self.mult1 = float(params.get("mult1", 1.0))
        self.mult2 = float(params.get("mult2", 2.0))
        self.mult3 = float(params.get("mult3", 3.0))
        self.min_votes = int(params.get("min_votes", 2))
        self.bb_period = int(params.get("bb_period", 20))
        self.bb_std = float(params.get("bb_std", 2.0))
        self.squeeze_lookback = int(params.get("squeeze_lookback", 120))
        self.bw_th = float(params.get("bw_threshold", 0.15))

        cap = 100000
        self._h = np.empty(cap); self._l = np.empty(cap)
        self._c = np.empty(cap); self._v = np.empty(cap)
        self._i = 0

        # Supertrend state per layer: (direction, upper, lower, atr_sum_buffer)
        self._st = [
            {"dir": 1, "upper": 0.0, "lower": 0.0, "tr_buf": np.zeros(20)},
            {"dir": 1, "upper": 0.0, "lower": 0.0, "tr_buf": np.zeros(20)},
            {"dir": 1, "upper": 0.0, "lower": 0.0, "tr_buf": np.zeros(20)},
        ]
        self._st_periods = [self.atr_p1, self.atr_p2, self.atr_p3]
        self._st_mults = [self.mult1, self.mult2, self.mult3]
        for s in self._st:
            s["tr_buf"] = np.zeros(max(self._st_periods) + 1)
            s["tr_idx"] = 0

        # BB state
        self._bb_close_buf = np.zeros(self.bb_period + 5)
        self._bb_idx = 0

        # BW history
        self._bw_buf = np.zeros(self.squeeze_lookback + 20)
        self._bw_idx = 0

    def _update_supertrend(self, layer: int, high: float, low: float, close: float):
        s = self._st[layer]
        p = self._st_periods[layer]
        mult = self._st_mults[layer]
        n = self._i

        if n < 2:
            return

        # True Range
        tr = max(high - low, abs(high - self._c[n-2]), abs(low - self._c[n-2]))
        s["tr_buf"][s["tr_idx"] % (p + 1)] = tr
        s["tr_idx"] += 1

        if n < p + 1:
            return

        # ATR = SMA of TR over period
        atr = np.mean(s["tr_buf"][:p])

        hl2 = (high + low) / 2
        upper = hl2 + mult * atr
        lower = hl2 - mult * atr

        prev_dir = s["dir"]
        prev_upper = s["upper"]
        prev_lower = s["lower"]

        if close > upper:
            new_dir = 1
        elif close < lower:
            new_dir = -1
        else:
            new_dir = prev_dir

        if new_dir == 1:
            s["upper"] = min(upper, prev_upper) if prev_upper > 0 else upper
            s["lower"] = lower
        else:
            s["lower"] = max(lower, prev_lower) if prev_lower > 0 else lower
            s["upper"] = upper

        s["dir"] = new_dir

    def _update_bb(self, close: float):
        n = self._i
        self._bb_close_buf[self._bb_idx % self.bb_period] = close
        self._bb_idx += 1

    def _get_bb_width(self) -> float:
        n = self._i
        if n < self.bb_period:
            return 0.0
        seg = self._bb_close_buf[:self.bb_period]
        mid = np.mean(seg)
        std = np.std(seg) * self.bb_std
        if mid == 0:
            return 0.0
        return (2 * std) / mid

    def next(self, bar: Bar):
        i = self._i
        self._h[i] = bar.high; self._l[i] = bar.low
        self._c[i] = bar.close; self._v[i] = bar.volume
        self._i += 1
        n = self._i

        # Update indicators incrementally
        self._update_bb(bar.close)
        self._update_supertrend(0, bar.high, bar.low, bar.close)
        self._update_supertrend(1, bar.high, bar.low, bar.close)
        self._update_supertrend(2, bar.high, bar.low, bar.close)

        # Need enough warmup
        min_bars = max(self._st_periods) + self.bb_period + 5
        if n < min_bars:
            return None

        # Only generate signal every 5 bars
        if (n - 1) % 5 != 0:
            return None

        # --- Multi-Supertrend votes ---
        votes_up = sum(1 for s in self._st if s["dir"] == 1)
        votes_dn = sum(1 for s in self._st if s["dir"] == -1)

        if votes_up < self.min_votes and votes_dn < self.min_votes:
            return Signal(action="close", price=bar.close)

        direction = 1 if votes_up >= self.min_votes else -1

        # --- Bollinger Squeeze check ---
        bw = self._get_bb_width()
        if bw == 0:
            return Signal(action="close", price=bar.close)

        self._bw_buf[self._bw_idx % self.squeeze_lookback] = bw
        self._bw_idx += 1

        bw_count = min(self._bw_idx, self.squeeze_lookback)
        if bw_count < 20:
            return Signal(action="close", price=bar.close)

        bw_arr = self._bw_buf[:bw_count]
        bw_min = np.percentile(bw_arr, 10)
        bw_max = np.percentile(bw_arr, 90)
        if bw_max - bw_min < 1e-9:
            return Signal(action="close", price=bar.close)

        bw_norm = (bw - bw_min) / (bw_max - bw_min)

        # Check if bandwidth is expanding (recent 5 > previous 5 mean)
        recent5 = bw_arr[-5:] if len(bw_arr) >= 5 else bw_arr
        prev5 = bw_arr[-10:-5] if len(bw_arr) >= 10 else bw_arr[:5]
        expanding = np.mean(recent5) > np.mean(prev5) * 1.02 if len(prev5) > 0 else False

        # Squeeze state
        squeezed = bw_norm < self.bw_th

        if squeezed and not expanding:
            return Signal(action="close", price=bar.close)

        if direction == 1:
            return Signal(action="buy", price=bar.close)
        else:
            return Signal(action="sell", price=bar.close)

    @staticmethod
    def get_params_space() -> dict:
        return {
            "atr_p1": {"type": "int", "min": 8, "max": 14, "default": 10},
            "atr_p2": {"type": "int", "min": 9, "max": 15, "default": 11},
            "atr_p3": {"type": "int", "min": 10, "max": 16, "default": 12},
            "mult1": {"type": "float", "min": 0.5, "max": 2.0, "default": 1.0},
            "mult2": {"type": "float", "min": 1.0, "max": 3.0, "default": 2.0},
            "mult3": {"type": "float", "min": 2.0, "max": 4.0, "default": 3.0},
            "min_votes": {"type": "int", "min": 1, "max": 3, "default": 2},
            "bb_period": {"type": "int", "min": 14, "max": 30, "default": 20},
            "bb_std": {"type": "float", "min": 1.5, "max": 3.0, "default": 2.0},
            "squeeze_lookback": {"type": "int", "min": 60, "max": 200, "default": 120},
            "bw_threshold": {"type": "float", "min": 0.1, "max": 0.5, "default": 0.15},
        }