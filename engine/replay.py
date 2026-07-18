from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

from engine.backtester import Backtester, Bar, Position, Signal, Trade
from engine.events import EventEmitter

logger = logging.getLogger(__name__)


@dataclass
class Tick:
    """Intrabar tick: a single price event inside a bar."""
    t: float            # fractional time within bar [0,1)
    price: float
    volume: float
    side: int = 0       # +1 uptick, -1 downtick, 0 neutral (for spread modeling)


def synthesize_ticks(
    bar: Any,
    n_ticks: int = 20,
    seed: Optional[int] = None,
    rng: Optional[random.Random] = None,
) -> list[Tick]:
    """Synthesize a plausible intrabar tick path from OHLCV.

    Path guarantees: starts at open, ends at close, touches high and low
    somewhere in between. Volume is distributed across ticks proportional to
    local price move magnitude (more volume on bigger moves). Deterministic
    when seed/rng is fixed so replay is reproducible.

    Accepts either a pandas row (bar["open"]) or a Bar dataclass (bar.open).
    """
    if hasattr(bar, "open"):
        o, h, l, c, v = bar.open, bar.high, bar.low, bar.close, bar.volume
    else:
        o, h, l, c, v = bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"]
    if h < max(o, c) or l > min(o, c):
        # defensive: clamp high/low
        h = max(h, o, c)
        l = min(l, o, c)
    rng = rng or random.Random(seed)

    # Build a monotone-ish random walk from open to close, then force high/low.
    # Use n interior points; first=open, last=close.
    n = max(4, n_ticks)
    # random walk steps
    steps = rng.choices([-1, 1], k=n - 1)
    # bias toward closing price
    walk = [o]
    for i, s in enumerate(steps):
        prog = (i + 1) / (n)  # progress toward close
        target = o + (c - o) * prog
        noise = (h - l) * 0.15 * s * rng.random()
        walk.append(target + noise)
    walk[-1] = c
    walk[0] = o

    # Force high/low touch: insert a high spike and a low dip at random interior idx
    hi_idx = rng.randint(1, n - 2)
    lo_idx = rng.randint(1, n - 2)
    walk[hi_idx] = max(walk[hi_idx], h)
    walk[lo_idx] = min(walk[lo_idx], l)
    # ensure bounds
    walk = [min(max(p, l), h) for p in walk]

    ticks: list[Tick] = []
    total_v = v if v and v > 0 else float(n)
    # volume weights ~ |move|
    moves = [abs(walk[i + 1] - walk[i]) for i in range(n - 1)]
    tot = sum(moves) or 1.0
    for i in range(n - 1):
        t = i / (n - 1)
        price = walk[i]
        vol = total_v * (moves[i] / tot)
        side = 1 if walk[i + 1] >= walk[i] else -1
        ticks.append(Tick(t=t, price=price, volume=vol, side=side))
    # final tick at close (t=1.0)
    ticks.append(Tick(t=1.0, price=c, volume=total_v * 0.05, side=0))
    return ticks


class ReplayBacktester(Backtester):
    """Replay-grade backtester: tick-level intrabar execution.

    Extends Backtester but instead of filling at bar.close, it synthesizes
    intrabar ticks and fills signals at the exact tick they trigger:
      - market order: fills at the NEXT tick after signal (with slippage model)
      - limit order : rests in a queue; fills only when a tick price crosses it
      - stop order  : triggers when a tick price crosses the stop level

    This delivers replay-grade precision vs the legacy close-price fill.
    """

    def __init__(self, *args, ticks_per_bar: int = 20, tick_seed: Optional[int] = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.ticks_per_bar = ticks_per_bar
        self.tick_seed = tick_seed
        self._rng = random.Random(tick_seed) if tick_seed is not None else random.Random()
        # resting limit/stop orders carried across bars until filled or cancelled
        self._resting: list[dict] = []

    def set_data(self, data: pd.DataFrame) -> None:
        # allow optional 'metadata' column
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        if not required.issubset(data.columns):
            raise ValueError(f"Data must contain columns: {required}")
        self.data = data.sort_values("timestamp").reset_index(drop=True)

    def _next_tick_rng(self):
        # per-bar rng so each bar's path is reproducible but independent
        if self.tick_seed is not None:
            return random.Random(self.tick_seed + self._bar_hashes_seen)
        return self._rng

    _bar_hashes_seen = 0

    def run(self) -> Any:
        if self.strategy is None or self.data is None:
            raise ValueError("Strategy and data must be set")

        capital = self.initial_capital
        position: Optional[Position] = None
        equity_curve: list[float] = [capital]
        drawdown_curve: list[float] = [0.0]
        buy_hold_curve: list[float] = [capital]
        timestamps: list[Any] = [self.data.iloc[0].timestamp]
        trades: list[Trade] = []
        entry_bar = None
        entry_bar_index = None
        pending_signals: list[tuple[int, Any, Any]] = []
        delay = self.exchange.fill_delay_bars() if self.exchange is not None else 0
        self._bar_hashes_seen = 0

        def _fee_for(order_type, is_maker, notional=0.0, action=""):
            if self.market_engine is not None:
                return self.market_engine.commission(notional, is_open=(action in ("buy", "sell")))
            if self.exchange is not None:
                rate = self.exchange.fee_for(order_type, is_maker)
                return notional * rate
            return self.commission

        def _slip(direction):
            if self.market_engine is not None:
                return self.market_engine.slippage_factor(direction) - 1.0
            if self.exchange is not None:
                qty = abs(capital / self.data.iloc[0].close) if self.data.iloc[0].close else 0
                return self.exchange.slippage_for(depth=1000.0, qty=qty)
            return self.slippage

        def _size(price):
            if self.market_engine is not None:
                return self.market_engine.position_size(capital, price, self.leverage)
            return (capital * self.leverage) / price if self.perp is not None else capital / price

        def _open_position(sig, fill_price, bar, bar_index):
            nonlocal capital, position, entry_bar, entry_bar_index
            direction = 1 if sig.action == "buy" else -1
            slip = _slip(direction)
            fill_price = fill_price * (1 + slip * direction)
            notional = capital * (self.leverage if self.perp is not None else 1.0)
            fee = _fee_for("market", False, notional, action=sig.action)
            size = _size(fill_price)
            size = size if direction > 0 else -size
            position = Position(size=size, entry_price=fill_price, current_price=fill_price)
            capital -= fee
            entry_bar = bar.timestamp
            entry_bar_index = bar_index

        def _close_position(exit_price, bar, bar_index, reason="signal"):
            nonlocal capital, position, entry_bar, entry_bar_index
            if position is None:
                return
            direction = -1 if position.size > 0 else 1
            slip = _slip(direction)
            exit_price = exit_price * (1 + slip * direction)
            pnl = position.size * (exit_price - position.entry_price)
            fee = _fee_for("market", False, abs(position.size) * position.entry_price, action="close")
            pnl -= fee
            funding_paid = 0.0
            if self.funding is not None:
                notional = abs(position.size) * position.entry_price
                side = 1 if position.size > 0 else -1
                funding_paid = notional * self.funding.accrued(entry_bar, bar.timestamp, side)
                pnl -= funding_paid
            tr = Trade(
                entry_time=entry_bar or bar.timestamp, entry_price=position.entry_price,
                size=abs(position.size), exit_time=bar.timestamp, exit_price=exit_price,
                pnl=pnl, funding_paid=funding_paid,
                direction="long" if position.size > 0 else "short",
                exit_reason=reason,
                holding_bars=(bar_index - entry_bar_index) if entry_bar_index is not None else 0,
            )
            trades.append(tr)
            capital += pnl
            position = None
            entry_bar = None
            entry_bar_index = None

        for i, (_, row) in enumerate(self.data.iterrows()):
            self._bar_hashes_seen += 1
            bar = Bar(
                timestamp=row["timestamp"], open=row["open"], high=row["high"],
                low=row["low"], close=row["close"], volume=row["volume"],
                metadata=dict(row["metadata"]) if "metadata" in row and isinstance(row.get("metadata"), dict) else None,
            )
            ticks = synthesize_ticks(bar, n_ticks=self.ticks_per_bar, rng=self._next_tick_rng())

            # ── resting orders first: check fills at each tick ──
            if self._resting:
                still = []
                for order in self._resting:
                    filled = False
                    for tk in ticks:
                        if order["type"] == "limit":
                            if order["direction"] > 0 and tk.price <= order["price"]:
                                _open_position(order["sig"], order["price"], bar, i) if order["sig"].action in ("buy", "sell") and position is None else None
                                filled = True
                                break
                            if order["direction"] < 0 and tk.price >= order["price"]:
                                _open_position(order["sig"], order["price"], bar, i) if order["sig"].action in ("sell",) and position is None else None
                                filled = True
                                break
                        elif order["type"] == "stop":
                            if order["direction"] > 0 and tk.price >= order["price"]:
                                _open_position(order["sig"], tk.price, bar, i)
                                filled = True
                                break
                            if order["direction"] < 0 and tk.price <= order["price"]:
                                _open_position(order["sig"], tk.price, bar, i)
                                filled = True
                                break
                    if not filled:
                        still.append(order)
                self._resting = still

            # ── strategy signal on the bar (sampled at open tick) ──
            signal = self.strategy.next(bar)
            if signal:
                self.events.emit("signal", signal)
                if self.market_engine is not None and not self.market_engine.can_execute(bar.timestamp):
                    signal = None
                if signal is not None:
                    # schedule execution across ticks within this bar
                    if signal.order_type == "limit" and signal.price is not None:
                        # rest the limit order (queue) — only fills if price touches
                        self._resting.append({
                            "type": "limit",
                            "price": signal.price,
                            "direction": 1 if signal.action == "buy" else -1,
                            "sig": signal,
                        })
                    elif signal.order_type == "stop" and signal.price is not None:
                        self._resting.append({
                            "type": "stop",
                            "price": signal.price,
                            "direction": 1 if signal.action == "buy" else -1,
                            "sig": signal,
                        })
                    elif signal.action in ("buy", "sell") and position is None:
                        # market: fill at next tick (skip open tick)
                        if len(ticks) > 1:
                            _open_position(signal, ticks[1].price, bar, i)
                    elif signal.action in ("close",) and position is not None:
                        if len(ticks) > 1:
                            _close_position(ticks[1].price, bar, i)

            # ── MTM at close ──
            if position is not None:
                position.current_price = bar.close
                position.pnl = position.size * (bar.close - position.entry_price)
                position.pnl_pct = position.pnl / capital * 100
            self.strategy.position = position

            if self.market_engine is not None and position is not None:
                hook = self.market_engine.on_bar(bar, bar.timestamp, None)
                if hook.get("funding_fee"):
                    capital -= hook["funding_fee"]
                if hook.get("swap_fee"):
                    capital -= hook["swap_fee"]
                if hook.get("liquidated"):
                    slip = self.market_engine.slippage_factor(-1 if position.size > 0 else 1) - 1.0
                    exit_price = bar.close * (1 + slip * (-1 if position.size > 0 else 1))
                    _close_position(exit_price, bar, i, reason="liquidation")

            current_equity = capital + (position.pnl if position else 0)
            equity_curve.append(current_equity)
            peak = max(equity_curve)
            dd = (peak - current_equity) / peak * 100
            drawdown_curve.append(dd)
            timestamps.append(bar.timestamp)
            if len(buy_hold_curve) == 1:
                buy_hold_curve.append(capital)
            else:
                base_close = self.data.iloc[0].close
                buy_hold_curve.append(capital * (bar.close / base_close))

        return self._calculate_metrics(trades, equity_curve, drawdown_curve, buy_hold_curve, timestamps)
