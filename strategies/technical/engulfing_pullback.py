from __future__ import annotations

from typing import Any, Optional

import numpy as np

from strategies.base import Bar, Signal, StrategyBase


class EngulfingPullbackStrategy(StrategyBase):
    """EMA200 + ADX14 趋势过滤 + 回调吞没（engulfing）进场 + 2R 出場。

    规则：
      - 趋势方向由 EMA200 斜率判定（ema > ema_prev → 偏多）
      - ADX14 >= adx_threshold 视为趋势有效，才允许进场
      - 空仓时等价格回调至 EMA200 附近（|close-ema|/atr <= pullback_atr），
        出现看涨/看跌吞没形态触发多/空
      - SL = 进场 bar 的 swing 极（多：bar.low；空：bar.high）；
        若用 ATR 模式则 SL = entry -/+ sl_atr_mult*ATR
      - TP（2R）= entry + 2*(entry-SL)  [多头]；对称空头
    指标手算（滚动窗口），避免 pandas_ta 全量重算。
    """

    name = "engulfing_pullback"
    description = "EMA200+ADX14趋势过滤 + 回调吞没进场 + 2R出場"
    category = "trend"

    def init(self, params: dict[str, Any]) -> None:
        super().init(params)
        self.ema_len: int = int(params.get("ema_len", 200))
        self.adx_len: int = int(params.get("adx_len", 14))
        self.atr_len: int = int(params.get("atr_len", 14))
        self.adx_threshold: float = float(params.get("adx_threshold", 20.0))
        self.pullback_atr: float = float(params.get("pullback_atr", 1.5))
        self.sl_atr_mult: float = float(params.get("sl_atr_mult", 1.0))
        self.rr_ratio: float = float(params.get("rr_ratio", 2.0))  # 2R 出場
        self.use_atr_sl: bool = bool(params.get("use_atr_sl", False))

        # 滚动历史
        self._closes: list[float] = []
        self._highs: list[float] = []
        self._lows: list[float] = []
        self._opens: list[float] = []

        # 持仓状态机
        self._pos: int = 0       # -1 short, 0 flat, +1 long
        self._entry: float = 0.0
        self._sl: float = 0.0
        self._tp: float = 0.0

    # ── 指标（手算）──
    def _ema(self, vals: list[float], period: int) -> Optional[float]:
        if len(vals) < period:
            return None
        arr = np.asarray(vals[-period * 3:], dtype=float)
        alpha = 2.0 / (period + 1)
        ema = arr[:period].mean()
        for v in arr[period:]:
            ema = alpha * v + (1 - alpha) * ema
        return float(ema)

    def _atr(self, period: int) -> Optional[float]:
        n = len(self._closes)
        if n < period + 1:
            return None
        trs = []
        for i in range(n - period, n):
            h, l, c_prev = self._highs[i], self._lows[i], self._closes[i - 1]
            trs.append(max(h - l, abs(h - c_prev), abs(l - c_prev)))
        return float(np.mean(trs))

    def _adx(self, period: int) -> Optional[float]:
        n = len(self._closes)
        if n < period * 2 + 1:
            return None
        # Only need a recent window: Wilder smoothing converges, older bars
        # contribute <1% after ~period*4 bars. Avoids O(n^2) on long series.
        win = period * 4
        hi = self._highs[-win:] if win < n else self._highs
        lo = self._lows[-win:] if win < n else self._lows
        cl = self._closes[-win:] if win < n else self._closes
        m = len(cl)
        plus_dm, minus_dm, tr = [], [], []
        for i in range(1, m):
            up = hi[i] - hi[i - 1]
            dn = lo[i - 1] - lo[i]
            plus_dm.append(max(up, 0.0) if up > dn else 0.0)
            minus_dm.append(max(dn, 0.0) if dn > up else 0.0)
            tr.append(max(
                hi[i] - lo[i],
                abs(hi[i] - cl[i - 1]),
                abs(lo[i] - cl[i - 1]),
            ))
        # Wilder smoothing
        def wilder(series: list[float]) -> float:
            s = sum(series[:period]) / period
            for v in series[period:]:
                s = (s * (period - 1) + v) / period
            return s
        atr = wilder(tr)
        pdm = wilder(plus_dm)
        mdm = wilder(minus_dm)
        pdi = 100 * pdm / atr if atr > 0 else 0.0
        mdi = 100 * mdm / atr if atr > 0 else 0.0
        dx = 100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) > 0 else 0.0
        dxs = []
        for i in range(period, len(plus_dm)):
            up = plus_dm[i] - minus_dm[i] if plus_dm[i] > minus_dm[i] else 0.0
            dn = minus_dm[i] - plus_dm[i] if minus_dm[i] > plus_dm[i] else 0.0
            atr = (atr * (period - 1) + tr[i]) / period
            pdm = (pdm * (period - 1) + up) / period
            mdm = (mdm * (period - 1) + dn) / period
            pdi = 100 * pdm / atr if atr > 0 else 0.0
            mdi = 100 * mdm / atr if atr > 0 else 0.0
            dxv = 100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) > 0 else 0.0
            dxs.append(dxv)
        return float(np.mean(dxs)) if dxs else None

    # ── 吞没形态 ──
    def _bullish_engulfing(self) -> bool:
        if len(self._closes) < 2:
            return False
        o1, c1 = self._opens[-2], self._closes[-2]   # 前一根（阴）
        o2, c2 = self._opens[-1], self._closes[-1]   # 当前根（阳）
        return c1 < o1 and c2 > o2 and c2 > o1 and o2 < c1

    def _bearish_engulfing(self) -> bool:
        if len(self._closes) < 2:
            return False
        o1, c1 = self._opens[-2], self._closes[-2]   # 前一根（阳）
        o2, c2 = self._opens[-1], self._closes[-1]   # 当前根（阴）
        return c1 > o1 and c2 < o2 and c2 < o1 and o2 > c1

    def next(self, bar: Bar) -> Optional[Signal]:
        self._opens.append(bar.open)
        self._closes.append(bar.close)
        self._highs.append(bar.high)
        self._lows.append(bar.low)

        if len(self._closes) < self.ema_len + self.adx_len * 2 + 1:
            return None

        close = bar.close
        ema = self._ema(self._closes, self.ema_len)
        ema_prev = self._ema(self._closes[:-1], self.ema_len)
        atr = self._atr(self.atr_len)
        adx = self._adx(self.adx_len)
        if ema is None or ema_prev is None or atr is None or atr == 0 or adx is None:
            return None

        # ── 持仓中：SL/TP 触价 ──
        if self._pos != 0:
            if self._pos > 0:  # LONG
                if bar.low <= self._sl or bar.high >= self._tp:
                    return self._close()
            else:  # SHORT
                if bar.high >= self._sl or bar.low <= self._tp:
                    return self._close()
            return None

        # ── 空仓：趋势过滤 + 回调吞没 ──
        ema_slope_up = ema > ema_prev
        trend_strong = adx >= self.adx_threshold
        # 回调至 EMA 附近：价格贴近 EMA（距离 <= pullback_atr 倍 ATR）
        near_ema = abs(close - ema) / atr <= self.pullback_atr

        # 多头：趋势向上 + ADX 强 + 回踩 EMA + 看涨吞没
        if ema_slope_up and trend_strong and near_ema and self._bullish_engulfing():
            self._pos = 1
            self._entry = close
            self._sl = (close - atr * self.sl_atr_mult) if self.use_atr_sl else bar.low
            self._tp = self._entry + self.rr_ratio * (self._entry - self._sl)
            return Signal(action="buy", price=close,
                          stop_loss=self._sl, take_profit=self._tp)

        # 空头：趋势向下 + ADX 强 + 回踩 EMA + 看跌吞没
        if (not ema_slope_up) and trend_strong and near_ema and self._bearish_engulfing():
            self._pos = -1
            self._entry = close
            self._sl = (close + atr * self.sl_atr_mult) if self.use_atr_sl else bar.high
            self._tp = self._entry - self.rr_ratio * (self._sl - self._entry)
            return Signal(action="sell", price=close,
                          stop_loss=self._sl, take_profit=self._tp)
        return None

    def _close(self) -> Signal:
        sig = Signal(action="close", price=self._entry)
        self._pos = 0
        self._entry = 0.0
        self._sl = 0.0
        self._tp = 0.0
        return sig

    def get_params_space(self) -> dict[str, Any]:
        return {
            "ema_len": {"type": "range", "min": 50, "max": 300, "step": 10},
            "adx_len": {"type": "range", "min": 7, "max": 30, "step": 1},
            "atr_len": {"type": "range", "min": 7, "max": 30, "step": 1},
            "adx_threshold": {"type": "range", "min": 10, "max": 40, "step": 1},
            "pullback_atr": {"type": "range", "min": 0.5, "max": 4.0, "step": 0.1},
            "sl_atr_mult": {"type": "range", "min": 0.5, "max": 3.0, "step": 0.1},
            "rr_ratio": {"type": "range", "min": 1.0, "max": 4.0, "step": 0.1},
            "use_atr_sl": {"type": "choice", "values": [True, False]},
        }

    def warmup_period(self) -> int:
        return self.ema_len + self.adx_len * 2 + 1
