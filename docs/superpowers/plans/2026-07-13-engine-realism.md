# Backtest Realism Engine (Funding / Liquidation / Maker-Taker / Exchange-Sim / ms-Time) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the spot-1x `engine/backtester.py` into a composable engine that supports perpetual-futures realism: historical funding accrual, leverage/margin/mark-price liquidation, maker/taker fee differentiation, exchange-environment simulation (latency/rate-limit/fill-probability/slippage), and millisecond timestamp fidelity — all opt-in via `BacktestConfig` so existing 1x spot backtests stay unchanged.

**Architecture:** Add three focused engine modules — `engine/funding.py` (funding-rate accrual), `engine/perpetual.py` (leverage/margin/mark-price/liquidation), `engine/exchange.py` (fee model + environment sim). The `Backtester` core loop is refactored to consult an optional `ExchangeModel` and optional `PerpSimulator` passed in `__init__`; when both are `None` the engine behaves exactly as today (backward compatible). `BacktestConfig` gains optional `perpetual`, `exchange`, `funding` sub-configs. Data layer stops truncating timestamps to seconds (item 1 already float64-safe). Each feature is independently testable via `tests_backend/`.

**Tech Stack:** Python 3.12, pandas, numpy, FastAPI (schemas), pytest. No new runtime deps.

## Global Constraints
- Backward compatibility: a `BacktestConfig` WITHOUT `perpetual`/`exchange`/`funding` MUST produce identical metrics to the current engine (regression test required).
- All prices stay `float64` (item 1 verified safe); do NOT introduce `Decimal` (YAGNI, slows vector path). Only fix timestamp precision.
- Precision: no `round()` on prices inside the loop; funding/margin math in `float64`.
- New engine modules live under `engine/` and are imported lazily by `BacktestService` so a missing config field never breaks the 1x path.
- POLLUTION GUARD: backend tests must not call the upload/git-push entrypoint; load strategies from `strategies/technical/` or temp files only.
- Commit after every task. Each task = one independently testable deliverable.

## File Structure
- Create: `engine/funding.py` — `FundingSchedule`, `FundingModel` (rate lookup + accrual over held interval)
- Create: `engine/perpetual.py` — `PerpSimulator` (leverage, margin, maintenance, mark price, liquidation check), `LiquidationError`
- Create: `engine/exchange.py` — `ExchangeModel` (maker/taker fee decision, latency bars, rate-limit throttle, fill probability, book-depth slippage)
- Modify: `engine/backtester.py` — accept optional `perp`, `exchange`, `funding`; apply in loop
- Modify: `app/models/schemas.py` — add `PerpetualConfig`, `ExchangeConfig`, `FundingConfig`; extend `BacktestConfig`
- Modify: `app/services/backtest_service.py` — build `perp`/`exchange`/`funding` from config, pass to `Backtester`
- Modify: `app/api/routes/data.py` — keep millisecond precision (remove `//10**9` truncation; emit ms int)
- Modify: `strategies/base.py` — `Bar` gains optional `mark_price: Optional[float]`; `Signal` gains `order_type: str = "market"`
- Test: `tests_backend/test_funding.py`, `test_perpetual.py`, `test_exchange.py`, `test_backtester_realistic.py`, `test_data_ms.py`

---

### Task 1: Funding data model + accrual (item 2 core)

**Files:**
- Create: `engine/funding.py`
- Test: `tests_backend/test_funding.py`

**Interfaces:**
- Consumes: pandas `Series` of historical funding rates (index=Timestamp, value=rate fraction e.g. 0.0001)
- Produces: `FundingModel.accrued(entry, exit, side) -> float` (signed funding paid/received in quote currency terms, as fraction of notional)

- [ ] **Step 1: Write failing test**
```python
# tests_backend/test_funding.py
import pandas as pd
from engine.funding import FundingModel, FundingSchedule

def test_accrual_over_two_intervals():
    idx = pd.to_datetime(["2024-01-01 00:00", "2024-01-01 08:00", "2024-01-01 16:00"])
    rates = pd.Series([0.0001, -0.0002, 0.0001], index=idx)
    fm = FundingModel(FundingSchedule(interval_hours=8, rates=rates))
    # long from 00:00 to 16:00 holds through 08:00 and 16:00 payments
    accrued = fm.accrued(pd.Timestamp("2024-01-01 00:00"), pd.Timestamp("2024-01-01 16:00"), side=1)
    # long pays positive rate, receives negative -> net = 0.0001 + (-0.0002) = -0.0001 of notional
    assert abs(accrued - (-0.0001)) < 1e-12
```
- [ ] **Step 2: Run test, expect FAIL** (`engine.funding` import error)
- [ ] **Step 3: Implement `engine/funding.py`**
```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

@dataclass
class FundingSchedule:
    interval_hours: int = 8
    rates: pd.Series = field(default_factory=pd.Series)  # index=Timestamp, value=rate fraction

class FundingModel:
    def __init__(self, schedule: Optional[FundingSchedule] = None, default_rate: float = 0.0):
        self.schedule = schedule
        self.default_rate = default_rate

    def rate_at(self, ts: pd.Timestamp) -> float:
        if self.schedule is None or self.schedule.rates.dropna().empty:
            return self.default_rate
        s = self.schedule.rates[self.schedule.rates.index <= ts]
        return float(s.iloc[-1]) if not s.empty else self.default_rate

    def accrued(self, entry: pd.Timestamp, exit: pd.Timestamp, side: int) -> float:
        """Signed funding as fraction of notional. Long(side=1) pays positive rate."""
        if self.schedule is None or self.schedule.rates.dropna().empty:
            r = self.default_rate
            return r * side * (self.schedule.interval_hours if self.schedule else 8) / 24.0 * 0.0  # no time-based w/o schedule
        s = self.schedule.rates[(self.schedule.rates.index > entry) & (self.schedule.rates.index <= exit)]
        total = float(s.sum())
        return total * side  # long pays positive funding out (negative pnl)
```
- [ ] **Step 4: Run test, expect PASS**
- [ ] **Step 5: Commit** `git add engine/funding.py tests_backend/test_funding.py && git commit -m "feat(engine): funding accrual model (item 2)"`

### Task 2: Wire funding into Backtester loop

**Files:**
- Modify: `engine/backtester.py` (add `funding` param to `__init__`, accrue on close)
- Modify: `tests_backend/test_backtester_realistic.py`

**Interfaces:**
- Consumes: `FundingModel` from Task 1
- Produces: `Trade.funding_paid` field; reflected in `pnl`

- [ ] **Step 1: Write failing test**
```python
def test_funding_reduces_long_pnl():
    import pandas as pd
    from engine.backtester import Backtester
    from engine.funding import FundingModel, FundingSchedule
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01 00:00","2024-01-01 08:00","2024-01-01 16:00"]),
        "open":[100,101,102],"high":[100,101,102],"low":[100,101,102],"close":[100,101,102],"volume":[1,1,1]})
    idx = pd.to_datetime(["2024-01-01 08:00"])
    fm = FundingModel(FundingSchedule(8, pd.Series([0.001], index=idx)))
    bt = Backtester(initial_capital=10000, commission=0, slippage=0, funding=fm)
    # minimal strategy: buy bar0, close bar2
    ...
```
- [ ] **Step 2-4:** implement `funding` param in `Backtester.__init__`, on `close` action compute `funding_paid = position.notional * fm.accrued(entry, exit, side)` and subtract from pnl; add `Trade.funding_paid`. Test passes.
- [ ] **Step 5: Commit**

### Task 3: PerpSimulator — leverage/margin/mark-price/liquidation (item 3)

**Files:**
- Create: `engine/perpetual.py`
- Test: `tests_backend/test_perpetual.py`

**Interfaces:**
- Produces: `PerpSimulator.check_liquidation(mark_price, entry_price, size, leverage, maint_margin_rate) -> bool`, `margin_required(notional, leverage)`, `position_pnl(...)`

- [ ] **Step 1: Test**
```python
from engine.perpetual import PerpSimulator, LiquidationError
def test_liquidation_on_wick():
    ps = PerpSimulator(maintenance_margin_rate=0.005)
    # 10x long entry 100, margin = notional/10. liq when loss >= margin*(1-maint)
    # mark drops to 91 -> loss 9% -> margin 10%, maint 0.5% -> liquidated
    assert ps.check_liquidation(mark_price=91.0, entry_price=100.0, size=1.0, leverage=10.0) is True
    assert ps.check_liquidation(mark_price=95.0, entry_price=100.0, size=1.0, leverage=10.0) is False
```
- [ ] **Step 2-4:** implement `PerpSimulator` with exact liquidation formula: `liq = entry*(1 - (1-maint)/leverage*sign)` for long; check `mark <= liq`. Add `LiquidationError`. Test passes.
- [ ] **Step 5: Commit**

### Task 4: Wire PerpSimulator into Backtester (leverage + liq exit)

**Files:**
- Modify: `engine/backtester.py` (accept `perp: Optional[PerpSimulator]`, `leverage`)
- Test: `tests_backend/test_backtester_realistic.py`

- [ ] **Step 1: Test** — 10x long, price wicks to liq level on a low → position force-closed at mark, trade flagged `liquidated=True`, equity reflects loss.
- [ ] **Step 2-4:** in loop, when `perp` set: `size = capital*leverage/price`; each bar compute `mark = bar.low if long else bar.high` (worse-case wick); if `perp.check_liquidation(mark,...)` → force close at mark, set `Trade.liquidated=True`. Test passes.
- [ ] **Step 5: Commit**

### Task 5: ExchangeModel — maker/taker fee + environment sim (items 4 & 5)

**Files:**
- Create: `engine/exchange.py`
- Test: `tests_backend/test_exchange.py`

**Interfaces:**
- Produces: `ExchangeModel.fee_for(order_type, is_maker) -> float`, `ExchangeModel.slippage_for(book_depth, qty) -> float`, `ExchangeModel.fill_delay_bars() -> int`, `ExchangeModel.fill_probability(book_depth, qty) -> float`

- [ ] **Step 1: Test**
```python
from engine.exchange import ExchangeModel
def test_maker_cheaper_than_taker():
    em = ExchangeModel(maker_fee=0.0002, taker_fee=0.0005)
    assert em.fee_for("limit", True) == 0.0002
    assert em.fee_for("market", False) == 0.0005
def test_thin_book_more_slippage():
    em = ExchangeModel()
    assert em.slippage_for(depth=10.0, qty=5.0) > em.slippage_for(depth=1000.0, qty=5.0)
```
- [ ] **Step 2-4:** implement `ExchangeModel` with `maker_fee`, `taker_fee`, `latency_bars`, `rate_limit_per_min`, `book_depth_fn`. fee_for returns rate; slippage_for = base * qty/depth; fill_delay_bars returns `latency_bars`; fill_probability = clamp(1 - qty/depth). Test passes.
- [ ] **Step 5: Commit**

### Task 6: Wire ExchangeModel into Backtester (fee/slippage/fill)

**Files:**
- Modify: `engine/backtester.py` (accept `exchange: Optional[ExchangeModel]`)
- Test: `tests_backend/test_backtester_realistic.py`

- [ ] **Step 1: Test** — with `exchange` set and limit order (maker), commission uses maker rate; with market (taker), taker rate; slippage scales with qty/depth; fill delayed by `latency_bars` (signal executed N bars later).
- [ ] **Step 2-4:** replace hardcoded `commission`/`slippage` with `exchange.fee_for(...)` and `exchange.slippage_for(...)`; buffer signals by `latency_bars` when set. Test passes.
- [ ] **Step 5: Commit**

### Task 7: Schemas — PerpetualConfig / ExchangeConfig / FundingConfig

**Files:**
- Modify: `app/models/schemas.py` (add 3 configs + extend `BacktestConfig`)
- Modify: `strategies/base.py` (`Bar.mark_price`, `Signal.order_type`)

- [ ] **Step 1: Add to schemas.py**
```python
class FundingConfig(BaseModel):
    enabled: bool = False
    interval_hours: int = 8
    default_rate: float = 0.0

class PerpetualConfig(BaseModel):
    enabled: bool = False
    leverage: float = 1.0
    maintenance_margin_rate: float = 0.005

class ExchangeConfig(BaseModel):
    enabled: bool = False
    maker_fee: float = 0.0002
    taker_fee: float = 0.0005
    latency_bars: int = 0
    simulate_book: bool = False

# extend BacktestConfig:
#   funding: FundingConfig = Field(default_factory=FundingConfig)
#   perpetual: PerpetualConfig = Field(default_factory=PerpetualConfig)
#   exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
```
- [ ] **Step 2:** add `mark_price: Optional[float] = None` to `Bar`; `order_type: str = "market"` to `Signal` in `strategies/base.py`.
- [ ] **Step 3:** write test asserting schema defaults keep 1x path untouched.
- [ ] **Step 4: Commit**

### Task 8: BacktestService — build realism models from config

**Files:**
- Modify: `app/services/backtest_service.py`

- [ ] **Step 1: Test** — pass `perpetual={"enabled":True,"leverage":10}` → service constructs `PerpSimulator` and passes to `Backtester`; default (no keys) → both None (backward compat).
- [ ] **Step 2:** import `PerpSimulator`, `ExchangeModel`, `FundingModel`; in `run()`, build each only when `config["perpetual"]["enabled"]` etc. Pass as kwargs.
- [ ] **Step 3: Commit**

### Task 9: Millisecond timestamp fidelity (item 6)

**Files:**
- Modify: `app/api/routes/data.py:30` (emit ms, not seconds)
- Modify: `app/services/data_service.py` (keep ms through load)
- Test: `tests_backend/test_data_ms.py`

- [ ] **Step 1: Test** — `get_ohlcv` returns timestamp as int ms; two adjacent bars differ by <1000ms preserved.
- [ ] **Step 2:** change `out["timestamp"] = out["timestamp"].astype("int64") // 10**6` (ms). Update `OHLCVPoint` if needed (timestamp type int).
- [ ] **Step 3: Test passes; Commit**

### Task 10: Full regression — 1x spot path unchanged

**Files:**
- Test: `tests_backend/test_backtester_realistic.py` (add backward-compat assertion)

- [ ] **Step 1:** run current `tests_backend/test_backtester.py` + new realistic tests; assert a `Backtester()` with no perp/exchange/funding yields identical metrics to a pre-change baseline snapshot.
- [ ] **Step 2:** if any drift, fix. Commit `chore: lock 1x regression baseline`.
