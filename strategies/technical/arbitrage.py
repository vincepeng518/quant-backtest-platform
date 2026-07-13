from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

import numpy as np

from strategies.base import Bar, Signal, StrategyBase


class StatisticalArbitrageStrategy(StrategyBase):
    """統計套利：使用 OU 過程建模雙標的價差均值回歸。

    在 init 時透過 BingX 預載第二標的（symbol_b）全程收盤價，
    next 中以 log 價差擬合 OU 過程並產生 Z-Score 進出場訊號。
    """

    name = "stat_arb"
    description = "統計套利策略"
    category = "mean_reversion"

    def init(self, params: dict[str, Any]) -> None:
        super().init(params)
        self.lookback = int(params.get("lookback", 200))
        self.entry_z = float(params.get("entry_z", 1.5))
        self.exit_z = float(params.get("exit_z", 0.3))
        self.symbol_b = params.get("symbol_b", "ETH/USDT")
        self.refit_interval = int(params.get("refit_interval", 100))
        self.spread: list[float] = []
        self.leg2: list[float] = []
        self._ou_cache: tuple[float, float] | None = None
        self._ou_cache_at: int = -1
        self._load_leg2()

    @lru_cache(maxsize=8)
    def _fetch_close(self, symbol: str, timeframe: str = "1h") -> tuple:
        try:
            import ccxt

            ex = ccxt.bingx()
            ex.timeout = 20000
            raw = ex.fetch_ohlcv(symbol, timeframe, limit=1500)
            return tuple(r[4] for r in raw)
        except Exception:
            # fallback: generate synthetic leg2 so test mode has a real pair
            try:
                from data.providers.test_data import generate_test_data

                df = generate_test_data(symbol.replace("/", "_"))
                if df is not None and len(df) > 0:
                    return tuple(float(x) for x in df["close"].tolist())
            except Exception:
                pass
            return tuple()

    def _load_leg2(self) -> None:
        try:
            closes = self._fetch_close(self.symbol_b)
            self.leg2 = list(closes)
        except Exception:
            self.leg2 = []

    def _fit_ou(self, window) -> tuple[float, float]:
        arr = np.asarray(window, dtype=float)
        spread = arr - np.mean(arr)
        ds = np.diff(spread)
        s_lag = spread[:-1]
        A = np.vstack([s_lag, np.ones_like(s_lag)]).T
        slope, intercept = np.linalg.lstsq(A, ds, rcond=None)[0]
        kappa = -slope
        mu = intercept / kappa if kappa > 0 else float(np.mean(spread))
        return kappa, mu

    def next(self, bar: Bar) -> Optional[Signal]:
        idx = len(self.spread)
        if idx < len(self.leg2) and self.leg2[idx] > 0:
            spread_val = float(np.log(bar.close) - np.log(self.leg2[idx]))
        else:
            spread_val = bar.close
        self.spread.append(spread_val)

        if len(self.spread) < self.lookback:
            return None

        # rolling lookback window only (O(lookback), not O(n))
        window_arr = np.asarray(self.spread[-self.lookback:], dtype=float)
        mean = float(np.mean(window_arr))
        std = float(np.std(window_arr))
        if std == 0:
            return None

        # refit OU only every refit_interval bars (lstsq is the hot path)
        if self._ou_cache is None or (len(self.spread) - self._ou_cache_at) >= self.refit_interval:
            self._ou_cache = self._fit_ou(window_arr)
            self._ou_cache_at = len(self.spread)
        kappa, mu = self._ou_cache

        z = (self.spread[-1] - mean - mu) / std

        if z > self.entry_z and (self.position is None or self.position.size == 0):
            return Signal(action="sell", price=bar.close, metadata={"z": z, "kappa": kappa})
        if z < -self.entry_z and (self.position is None or self.position.size == 0):
            return Signal(action="buy", price=bar.close, metadata={"z": z, "kappa": kappa})
        if abs(z) < self.exit_z and self.position is not None:
            return Signal(action="close", metadata={"z": z})
        return None

    def warmup_period(self) -> int:
        return self.lookback

    def get_params(self) -> dict[str, Any]:
        return {
            "lookback": self.lookback,
            "entry_z": self.entry_z,
            "exit_z": self.exit_z,
            "symbol_b": self.symbol_b,
        }

    def get_params_space(self) -> dict[str, Any]:
        return {
            "lookback": {"type": "range", "min": 50, "max": 400, "step": 10},
            "entry_z": {"type": "range", "min": 1.0, "max": 3.0, "step": 0.1},
            "exit_z": {"type": "range", "min": 0.1, "max": 1.0, "step": 0.1},
            "refit_interval": {"type": "range", "min": 20, "max": 200, "step": 20},
        }
