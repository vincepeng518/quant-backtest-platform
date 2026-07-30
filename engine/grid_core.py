"""網格撮合狀態機 — 回測與實盤/模擬倉的**唯一**實作。

為什麼要有這個檔案
------------------
`/root/gridlab/grid2.py` 是向量化回測器, 一次吃完整個 DataFrame。
模擬倉/實盤是逐 tick 餵價格。如果兩邊各寫一份撮合邏輯, 必然發散
(過去已經因為 anchor 覆寫 / 單邊邊界檢查兩個 bug, 各自產生零價差捕獲與 -1.3M 假象)。

所以撮合規則只寫在這裡: 回測用 replay_bars() 驗證, 模擬倉用 on_price() 驅動。
`tests/test_grid_core_matches_backtest.py` 斷言兩者數字完全相同。

撮合規則 (勿改, 改了先跑驗證)
-----------------------------
1. anchor 是**整數格位**, 不是連續價格。價格必須跨越整整一格才成交,
   並帶 +/-1 hysteresis -> 同一格不會反覆買賣互抵。
2. 邊界必須**雙邊**檢查 lo <= px <= hi。只擋單邊會在跌破下界後持續賣出。
3. regime 夾住庫存方向: +1 只準 [0, cap], -1 只準 [-cap, 0], 0 為 [-cap, cap]。
4. 價格逼近邊界 recenter_gap 內 -> 以現價為中心重建網格, anchor 歸零。
5. 一根 K 線的掃描路徑: 陽線 low->high->close, 陰線 high->low->close。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Fill:
    side: str        # buy / sell
    price: float
    qty: float
    fee: float
    anchor: int


@dataclass
class GridState:
    """單一網格的撮合狀態。price-driven, 無 DataFrame 依賴。"""

    n_grids: int = 80
    qty: float = 0.0023
    fee_bps: float = 1.0        # maker
    taker_bps: float = 3.0
    recenter_gap: float = 1000.0
    cap_btc: float | None = None
    regime: int = 0             # +1 long-bias / 0 neutral / -1 short-bias
    recenter: bool = True

    # 運行狀態
    center: float = 0.0
    half_range: float = 0.0
    spacing: float = 0.0
    lo_b: float = 0.0
    hi_b: float = 0.0
    anchor: int = 0
    cash: float = 0.0
    pos: float = 0.0
    fees_paid: float = 0.0
    funding_paid: float = 0.0
    n_trades: int = 0
    n_recenter: int = 0
    n_flat: int = 0
    armed: bool = False
    fills: list = field(default_factory=list)
    keep_fills: bool = False

    # ── 生命週期 ────────────────────────────────────────────────
    def build(self, center: float, half_range: float) -> None:
        """以 center 為中心建立網格。"""
        self.center = float(center)
        self.half_range = float(half_range)
        self.spacing = 2.0 * self.half_range / self.n_grids
        self.lo_b = self.center - self.half_range
        self.hi_b = self.center + self.half_range
        self.anchor = 0
        self.armed = True

    def flatten(self, price: float) -> None:
        """市價平倉 (taker), 暫停網格。"""
        if self.pos != 0.0:
            self.cash += self.pos * price
            f = abs(self.pos) * price * (self.taker_bps / 10000.0)
            self.cash -= f
            self.fees_paid += f
            self.pos = 0.0
            self.n_flat += 1
        self.armed = False

    # ── 撮合 ────────────────────────────────────────────────────
    def _bounds(self) -> tuple[float, float]:
        cap = float("inf") if self.cap_btc is None else self.cap_btc
        if self.regime > 0:
            return 0.0, cap
        if self.regime < 0:
            return -cap, 0.0
        return -cap, cap

    def on_price(self, price: float) -> list:
        """餵一個價格點, 回傳本次成交清單。"""
        if not self.armed:
            return []
        pmin, pmax = self._bounds()
        fee = self.fee_bps / 10000.0
        out = []
        tgt = (price - self.center) / self.spacing
        while True:
            if tgt >= self.anchor + 1:
                self.anchor += 1
                px = self.center + self.anchor * self.spacing
                if self.lo_b - 1e-9 <= px <= self.hi_b + 1e-9 and self.pos - self.qty >= pmin - 1e-12:
                    self.cash += self.qty * px
                    self.pos -= self.qty
                    f = self.qty * px * fee
                    self.cash -= f
                    self.fees_paid += f
                    self.n_trades += 1
                    fl = Fill("sell", px, self.qty, f, self.anchor)
                    out.append(fl)
                    if self.keep_fills:
                        self.fills.append(fl)
            elif tgt <= self.anchor - 1:
                self.anchor -= 1
                px = self.center + self.anchor * self.spacing
                if self.lo_b - 1e-9 <= px <= self.hi_b + 1e-9 and self.pos + self.qty <= pmax + 1e-12:
                    self.cash -= self.qty * px
                    self.pos += self.qty
                    f = self.qty * px * fee
                    self.cash -= f
                    self.fees_paid += f
                    self.n_trades += 1
                    fl = Fill("buy", px, self.qty, f, self.anchor)
                    out.append(fl)
                    if self.keep_fills:
                        self.fills.append(fl)
            else:
                break
        return out

    def on_bar(self, o: float, h: float, l: float, c: float) -> list:
        """餵一根 K 線, 依陰陽線決定掃描路徑。"""
        path = (l, h, c) if c >= o else (h, l, c)
        out = []
        for p in path:
            out += self.on_price(p)
        return out

    def settle(self, close: float, funding_rate_8h: float = 0.0,
               minutes: float = 1.0, next_half_range: float | None = None) -> float:
        """收盤結算: 收付資金費, 必要時 recenter。回傳權益。"""
        if funding_rate_8h:
            fnd = self.pos * close * (funding_rate_8h / 480.0) * minutes
            self.cash -= fnd
            self.funding_paid += fnd
        eq = self.equity(close)
        if self.armed and self.recenter and (
            close - self.lo_b < self.recenter_gap or self.hi_b - close < self.recenter_gap
        ):
            self.build(close, next_half_range if next_half_range is not None else self.half_range)
            self.n_recenter += 1
        return eq

    def equity(self, price: float) -> float:
        return self.cash + self.pos * price

    def notional(self, price: float) -> float:
        return abs(self.pos) * price
