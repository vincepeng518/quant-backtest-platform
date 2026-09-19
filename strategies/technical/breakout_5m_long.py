"""5m 長回看突破策略（Jev 研究收斂版）— StrategyBase 子類。

來源
----
`research/breakout_jev/` 九階段研究的收斂結果。原始結論為「無統計顯著 edge」，
本策略存在的目的是讓標準優化管線（貝氏優化 → Walk-Forward → Monte Carlo）
能對它做嚴謹檢定，而不是為了實盤。

實證依據（400 天 BTC 1m → 5m 重採樣，115,202 根）
  - 短回看（12/24/96）全部負期望
  - 長回看（288 = 24h / 576 = 48h）零費率平均為正但不顯著
  - 小突破（brk_str < 0.28 ATR）優於大突破（+0.0410% vs -0.0322%）
  - 資產特定：BTC/FIL 為正，APT/SUI/BCH 為負
  - 統計檢定：所有配置 95% CI 跨零、時間不穩、多空不對稱 → 判定為雜訊

設計
----
1. 突破：close > 前 lookback 根的最高價（不含當根，無未來函數）
2. 進場：突破確立後以次根開盤市價進場（回測引擎的 Signal 機制）
3. 出場：OCO 停損/停利，以 ATR 倍數計算（絕對價格，引擎要求）
4. 方向：只做多（本策略用於趨勢延續；空單在研究中不穩定）

參數優化空間
  - lookback：96 ~ 720 根（覆蓋研究中有效的 288/576）
  - stop_atr：1.0 ~ 3.0
  - target_atr：2.0 ~ 6.0
  - brk_max_atr：0.2 ~ 1.0（小突破過濾，研究中發現的有效維度）

注意
----
- 引擎要求 stop_loss/take_profit 為**絕對價格**，不是百分比
- ATR 用 Wilder 平滑（alpha = 1/14），與研究腳本一致
- warmup_period 需 >= lookback + ATR 週期，否則前段無訊號
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

from strategies.base import Bar, Signal, StrategyBase


class Breakout5mLongStrategy(StrategyBase):
    """5m 長回看突破，只做多，ATR 停損停利。"""

    name = "breakout_5m_long"
    description = "5m 長回看突破（研究收斂版，只做多，ATR OCO）"
    category = "trend"

    # 預設值 = 研究中最被看好的配置
    DEFAULT_LOOKBACK = 576
    DEFAULT_STOP_ATR = 2.0
    DEFAULT_TARGET_ATR = 4.0
    DEFAULT_BRK_MAX = 0.28
    DEFAULT_MAX_HOLD = 288  # 最長持倉 288 根 5m = 24 小時
    ATR_PERIOD = 14

    def init(self, params: dict[str, Any]) -> None:
        super().init(params)
        self.lookback = int(params.get("lookback", self.DEFAULT_LOOKBACK))
        self.stop_atr = float(params.get("stop_atr", self.DEFAULT_STOP_ATR))
        self.target_atr = float(params.get("target_atr", self.DEFAULT_TARGET_ATR))
        self.brk_max = float(params.get("brk_max_atr", self.DEFAULT_BRK_MAX))

        self._highs: list[float] = []
        self._lows: list[float] = []
        self._closes: list[float] = []
        self._trs: list[float] = []
        self._atr: Optional[float] = None

        # 持倉狀態。**必須自行偵測出場** —— StrategyBase 沒有成交回調，
        # 引擎的 OCO 平倉不會通知策略；若只設 True 不設回 False，
        # 整個回測只會產生 1 筆交易（曾實際踩到，導致 WF/MC 結果全部無效）。
        self._in_pos: bool = False
        self._entry: float = 0.0
        self._stop_px: float = 0.0
        self._tgt_px: float = 0.0
        self._bars_held: int = 0
        self._max_hold: int = int(params.get("max_hold_bars", self.DEFAULT_MAX_HOLD))


    # ── ATR（Wilder 平滑，與研究腳本 ewm(alpha=1/14) 等價）──
    def _update_atr(self, bar: Bar) -> None:
        if self._closes:
            tr = max(
                bar.high - bar.low,
                abs(bar.high - self._closes[-1]),
                abs(bar.low - self._closes[-1]),
            )
        else:
            tr = bar.high - bar.low
        self._trs.append(tr)
        if len(self._trs) < self.ATR_PERIOD:
            self._atr = None
            return
        if self._atr is None:
            # 首值用簡單平均，之後 Wilder 遞推
            self._atr = float(np.mean(self._trs[-self.ATR_PERIOD:]))
        else:
            alpha = 1.0 / self.ATR_PERIOD
            self._atr = self._atr + alpha * (tr - self._atr)

    def next(self, bar: Bar) -> Optional[Signal]:
        # 先更新持倉狀態（自行偵測 OCO 出場 / 超時）
        if self._in_pos:
            self._bars_held += 1
            hit_stop = bar.low <= self._stop_px
            hit_tgt = bar.high >= self._tgt_px
            timed_out = self._bars_held >= self._max_hold
            if hit_stop or hit_tgt or timed_out:
                # 引擎已用 OCO 平倉；此處僅把內部狀態歸零以便下一次進場。
                # 回傳 close 是無害的（引擎對已平倉部位為 no-op），
                # 且能保證超時出場也真的被執行。
                self._in_pos = False
                self._bars_held = 0
                return Signal(action="close")

        self._highs.append(bar.high)
        self._lows.append(bar.low)
        self._update_atr(bar)
        self._closes.append(bar.close)

        if self._atr is None or len(self._highs) < self.lookback + 1:
            return None
        if self._atr <= 0:
            return None

        # 前 lookback 根的最高（不含當根 → 無未來函數）
        prior_high = max(self._highs[-self.lookback - 1 : -1])

        if self._in_pos:
            return None  # 持倉中

        if bar.close <= prior_high:
            return None

        # 突破幅度過濾（研究中發現小突破優於大突破）
        brk_strength = (bar.close - prior_high) / self._atr
        if brk_strength > self.brk_max:
            return None

        self._in_pos = True
        self._entry = bar.close
        self._stop_px = bar.close - self.stop_atr * self._atr
        self._tgt_px = bar.close + self.target_atr * self._atr
        self._bars_held = 0
        return Signal(
            action="buy",
            price=bar.close,
            stop_loss=self._stop_px,
            take_profit=self._tgt_px,
        )

    def get_params_space(self) -> dict[str, Any]:
        return {
            "lookback": {"type": "range", "min": 96, "max": 720, "step": 48},
            "stop_atr": {"type": "range", "min": 1.0, "max": 3.0, "step": 0.25},
            "target_atr": {"type": "range", "min": 2.0, "max": 6.0, "step": 0.5},
            "brk_max_atr": {"type": "range", "min": 0.2, "max": 1.0, "step": 0.1},
        }

    def get_params(self) -> dict[str, Any]:
        return {
            "lookback": self.lookback,
            "stop_atr": self.stop_atr,
            "target_atr": self.target_atr,
            "brk_max_atr": self.brk_max,
        }

    def warmup_period(self) -> int:
        return self.lookback + self.ATR_PERIOD + 1
