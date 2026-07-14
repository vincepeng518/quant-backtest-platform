from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

from strategies.base import Bar, Signal, StrategyBase


class EmaAdxKlStrategy(StrategyBase):
    """EMA200 + ADX 趋势过滤 + KL 关键价位反转策略（永续回测版）。

    逻辑移植自用户实盘脚本：
      - EMA200 斜率判断趋势方向
      - ADX >= 阈值 视为趋势有效
      - 价格距 KL 关键位 >= 3 倍 ATR 视为有足够空间
      - 收盘价上穿/下穿 EMA200 触发多/空
      - 进场后以 ATR 倍数设 SL/TP（策略内部维护，触价返回 close）
    """

    name = "ema_adx_kl"
    description = "EMA200+ADX趋势过滤+KL关键价位反转"
    category = "trend"

    def init(self, params: dict[str, Any]) -> None:
        super().init(params)
        self.ema_len: int = int(params.get("ema_len", 200))
        self.adx_len: int = int(params.get("adx_len", 14))
        self.atr_len: int = int(params.get("atr_len", 14))
        self.adx_threshold: float = float(params.get("adx_threshold", 20.0))
        self.kl_long: float = float(params.get("kl_price_long", 70000.0))
        self.kl_short: float = float(params.get("kl_price_short", 60000.0))
        self.sl_atr_mult: float = float(params.get("sl_atr_mult", 1.0))
        self.tp_atr_mult: float = float(params.get("tp_atr_mult", 1.5))
        self.kl_atr_mult: float = float(params.get("kl_atr_mult", 3.0))

        # 动态支撑/压力位 (auto S/R)：避免手填 KL 常数
        self.sr_mode: str = str(params.get("sr_mode", "auto"))  # 'auto' | 'manual'
        self.sr_lookback: int = int(params.get("sr_lookback", 200))
        self.sr_res_pct: float = float(params.get("sr_res_pct", 0.80))  # 压力 = high 的 80 分位
        self.sr_sup_pct: float = float(params.get("sr_sup_pct", 0.20))  # 支撑 = low 的 20 分位

        # 滚动历史
        self._closes: list[float] = []
        self._highs: list[float] = []
        self._lows: list[float] = []

        # 持仓状态 (策略自身记账)
        self._pos: int = 0  # -1 short, 0 flat, +1 long
        self._entry: float = 0.0
        self._sl: float = 0.0
        self._tp: float = 0.0

    def _dynamic_sr(self) -> tuple[float, float]:
        """滚动窗口分位算压力/支撑，auto 模式每根 bar 自动更新。"""
        hi = np.asarray(self._highs[-self.sr_lookback:], dtype=float)
        lo = np.asarray(self._lows[-self.sr_lookback:], dtype=float)
        res = float(np.percentile(hi, self.sr_res_pct * 100)) if len(hi) else self.kl_long
        sup = float(np.percentile(lo, self.sr_sup_pct * 100)) if len(lo) else self.kl_short
        return res, sup

    # ── 指标计算（手算，不依赖 pandas_ta）──
    def _ema(self, vals: list[float], period: int) -> Optional[float]:
        if len(vals) < period:
            return None
        arr = np.asarray(vals[-period * 3:], dtype=float)
        span = period
        alpha = 2.0 / (span + 1)
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
        if n < period * 2:
            return None
        plus_dm, minus_dm, tr = [], [], []
        for i in range(1, n):
            up = self._highs[i] - self._highs[i - 1]
            dn = self._lows[i - 1] - self._lows[i]
            plus_dm.append(max(up, 0.0) if up > dn else 0.0)
            minus_dm.append(max(dn, 0.0) if dn > up else 0.0)
            tr.append(max(
                self._highs[i] - self._lows[i],
                abs(self._highs[i] - self._closes[i - 1]),
                abs(self._lows[i] - self._closes[i - 1]),
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
        # ADX = smoothed DX
        dxs = []
        for i in range(period, len(plus_dm)):
            up = plus_dm[i] - minus_dm[i] if plus_dm[i] > minus_dm[i] else 0.0
            dn = minus_dm[i] - plus_dm[i] if minus_dm[i] > plus_dm[i] else 0.0
            tr_i = tr[i]
            atr = (atr * (period - 1) + tr_i) / period
            pdm = (pdm * (period - 1) + up) / period
            mdm = (mdm * (period - 1) + dn) / period
            pdi = 100 * pdm / atr if atr > 0 else 0.0
            mdi = 100 * mdm / atr if atr > 0 else 0.0
            dxv = 100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) > 0 else 0.0
            dxs.append(dxv)
        return float(np.mean(dxs)) if dxs else None

    def next(self, bar: Bar) -> Optional[Signal]:
        self._closes.append(bar.close)
        self._highs.append(bar.high)
        self._lows.append(bar.low)

        if len(self._closes) < self.ema_len + self.adx_len * 2:
            return None

        close = bar.close
        ema = self._ema(self._closes, self.ema_len)
        ema_prev = self._ema(self._closes[:-1], self.ema_len)
        atr = self._atr(self.atr_len)
        adx = self._adx(self.adx_len)
        if ema is None or ema_prev is None or atr is None or atr == 0 or adx is None:
            return None

        # ── 持仓中：检查 SL/TP（用 bar 高低，模拟触价）──
        if self._pos != 0:
            if self._pos > 0:  # LONG
                if bar.low <= self._sl:
                    return self._close()
                if bar.high >= self._tp:
                    return self._close()
            else:  # SHORT
                if bar.high >= self._sl:
                    return self._close()
                if bar.low <= self._tp:
                    return self._close()
            return None

        # ── 空仓：检查进场 ──
        # 动态支撑/压力位：auto 模式用滚动分位带替代手填 KL 常数
        if self.sr_mode == 'auto':
            kl_long, kl_short = self._dynamic_sr()
        else:
            kl_long, kl_short = self.kl_long, self.kl_short

        ema_slope_up = ema > ema_prev
        price_above_ema = close > ema
        trend_strong = adx >= self.adx_threshold

        prev_close = self._closes[-2]
        cross_over = (prev_close <= ema_prev) and (close > ema)
        cross_under = (prev_close >= ema_prev) and (close < ema)

        # 多头
        kl_dist_long = abs(kl_long - close)
        kl_enough_long = (kl_dist_long / atr) >= self.kl_atr_mult
        bull_trend = price_above_ema and ema_slope_up
        if bull_trend and trend_strong and kl_enough_long and cross_over:
            self._pos = 1
            self._entry = close
            self._sl = close - atr * self.sl_atr_mult
            self._tp = close + atr * self.tp_atr_mult
            return Signal(
                action="buy", price=close,
                stop_loss=self._sl, take_profit=self._tp,
            )

        # 空头
        kl_dist_short = abs(close - kl_short)
        kl_enough_short = (kl_dist_short / atr) >= self.kl_atr_mult
        bear_trend = (not price_above_ema) and (not ema_slope_up)
        if bear_trend and trend_strong and kl_enough_short and cross_under:
            self._pos = -1
            self._entry = close
            self._sl = close + atr * self.sl_atr_mult
            self._tp = close - atr * self.tp_atr_mult
            return Signal(
                action="sell", price=close,
                stop_loss=self._sl, take_profit=self._tp,
            )
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
            "kl_price_long": {"type": "range", "min": 20000, "max": 200000, "step": 1000},
            "kl_price_short": {"type": "range", "min": 20000, "max": 200000, "step": 1000},
            "sl_atr_mult": {"type": "range", "min": 0.5, "max": 3.0, "step": 0.1},
            "tp_atr_mult": {"type": "range", "min": 0.5, "max": 4.0, "step": 0.1},
            "kl_atr_mult": {"type": "range", "min": 1.0, "max": 5.0, "step": 0.5},
            "sr_mode": {"type": "choice", "values": ["auto", "manual"]},
            "sr_lookback": {"type": "range", "min": 50, "max": 500, "step": 10},
            "sr_res_pct": {"type": "range", "min": 0.6, "max": 0.95, "step": 0.05},
            "sr_sup_pct": {"type": "range", "min": 0.05, "max": 0.4, "step": 0.05},
        }

    def warmup_period(self) -> int:
        return self.ema_len + self.adx_len * 2
