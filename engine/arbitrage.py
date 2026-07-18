"""Cross-exchange (venue) arbitrage engine.

Minimal but contract-grade: holds a *paired* long/short position across two
venues (two aligned OHLCV feeds) and captures the funding + fee basis. Reuses
the already-built realism models (FundingModel, PerpSimulator, ExchangeModel)
so per-venue maker/taker fees, slippage, funding and leverage all apply.

The core Backtester stays single-leg and untouched — this engine is a focused,
self-contained paired-leg executor (ponytail: don't over-engineer the main path).

Position math mirrors engine/backtester.py per-leg execution:
  - entry cost = notional * fee(maker/taker)
  - close pnl  = size * (exit - entry) - notional * fee
  - funding     accrued per interval while open (long pays positive rate)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

from engine.backtester import Trade
from strategies.base import Bar, Position

try:
    from engine.funding import FundingModel, FundingSchedule
except Exception:  # pragma: no cover
    FundingModel = FundingSchedule = None  # type: ignore[assignment]
try:
    from engine.perpetual import PerpSimulator
except Exception:  # pragma: no cover
    PerpSimulator = None  # type: ignore[assignment]
try:
    from engine.exchange import ExchangeModel
except Exception:  # pragma: no cover
    ExchangeModel = None  # type: ignore[assignment]


@dataclass
class ArbConfig:
    initial_capital: float = 100_000.0
    # fraction of capital deployed per leg (leverage applied on top)
    allocation_pct: float = 0.5
    leverage: float = 1.0
    entry_threshold: float = 0.003   # |basis| to open legs
    exit_threshold: float = 0.001    # |basis| to flatten (basis mode)
    # locked mode: hold the paired position until basis reaches unlock_threshold
    # (or crosses zero / reverses sign), i.e. "lock" the spread until it resolves.
    mode: str = "basis"              # "basis" | "locked"
    unlock_threshold: float = 0.01   # |basis| to unlock in locked mode
    # realism
    funding: Optional[Any] = None
    perp: Optional[Any] = None
    long_exchange: Optional[Any] = None
    short_exchange: Optional[Any] = None
    _entry_basis_sign: Optional[float] = None  # runtime: sign of basis at entry (locked mode)


@dataclass
class ArbResult:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    total_return: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    profit_factor: float = 0.0
    avg_trade: float = 0.0
    avg_winner: float = 0.0
    avg_loser: float = 0.0
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    drawdown_curve: list[float] = field(default_factory=list)
    timestamps: list[pd.Timestamp] = field(default_factory=list)


def _basis(long_close: float, short_close: float) -> float:
    """Relative price gap (short venue vs long venue). +ve => short venue dearer."""
    if long_close == 0:
        return 0.0
    return (short_close - long_close) / long_close


class ArbitrageEngine:
    def __init__(self, cfg: ArbConfig) -> None:
        self.cfg = cfg

    def run(self, long_data: pd.DataFrame, short_data: pd.DataFrame) -> ArbResult:
        cfg = self.cfg
        # Align on shared timestamp index (inner join — only trade when both venues have a bar)
        df = pd.merge(
            long_data.rename(columns=lambda c: f"L_{c}" if c != "timestamp" else c),
            short_data.rename(columns=lambda c: f"S_{c}" if c != "timestamp" else c),
            on="timestamp", how="inner",
        ).sort_values("timestamp").reset_index(drop=True)

        capital = cfg.initial_capital
        long_pos: Optional[Position] = None
        short_pos: Optional[Position] = None
        long_entry_bar: Optional[pd.Timestamp] = None
        short_entry_bar: Optional[pd.Timestamp] = None
        trades: list[Trade] = []
        equity_curve: list[float] = []
        drawdown_curve: list[float] = []
        timestamps: list[pd.Timestamp] = []

        def _fee(exch: Optional[ExchangeModel], order_type: str, is_maker: bool) -> float:
            if exch is not None:
                return exch.fee_for(order_type, is_maker)
            return 0.001

        def _leg_size(notional_cap: float, price: float) -> float:
            return (notional_cap * cfg.leverage) / price if cfg.perp is not None else notional_cap / price

        def _open_leg(side: int, price: float, exch: Optional[ExchangeModel], other_pos: Optional[Position], entry_bar_ts: pd.Timestamp) -> tuple[Position, float]:
            # side +1 long, -1 short
            order_type = "limit"
            is_maker = exch.decide_maker(order_type) if exch is not None else True
            fee_rate = _fee(exch, order_type, is_maker)
            notional = capital * cfg.allocation_pct
            cost = notional * fee_rate
            size = _leg_size(notional, price) * side
            pos = Position(size=size, entry_price=price, current_price=price)
            return pos, cost

        def _close_leg(pos: Position, price: float, exch: Optional[ExchangeModel], entry_bar_ts: pd.Timestamp, exit_bar_ts: pd.Timestamp, capital_ref: float) -> tuple[float, float]:
            order_type = "limit"
            is_maker = exch.decide_maker(order_type) if exch is not None else True
            fee_rate = _fee(exch, order_type, is_maker)
            notional = abs(pos.size) * pos.entry_price
            pnl = pos.size * (price - pos.entry_price)
            pnl -= notional * fee_rate
            funding_paid = 0.0
            if cfg.funding is not None:
                side = 1 if pos.size > 0 else -1
                frac = cfg.funding.accrued(entry_bar_ts, exit_bar_ts, side)
                funding_paid = notional * frac  # long positive => cost
                pnl -= funding_paid
            return pnl, funding_paid

        in_trade = False
        for _, row in df.iterrows():
            Lc = float(row["L_close"])
            Sc = float(row["S_close"])
            ts = row["timestamp"]
            basis = _basis(Lc, Sc)

            # Entry
            if not in_trade and abs(basis) >= cfg.entry_threshold:
                long_price = Lc * (1 + 0.0005)   # long pays ask-ish slippage
                short_price = Sc * (1 - 0.0005)
                long_pos, lc = _open_leg(1, long_price, cfg.long_exchange, None, ts)
                short_pos, sc = _open_leg(-1, short_price, cfg.short_exchange, None, ts)
                capital -= (lc + sc)
                long_entry_bar = ts
                short_entry_bar = ts
                cfg._entry_basis_sign = 1.0 if basis > 0 else -1.0
                in_trade = True

            # Exit
            elif in_trade and long_pos is not None and short_pos is not None:
                if cfg.mode == "locked":
                    # Lock the paired position: only flatten when the spread
                    # either blows past unlock_threshold (resolved) or reverses
                    # sign (the arb thesis is invalidated).
                    unlock = abs(basis) >= cfg.unlock_threshold
                    reversed_sign = (cfg._entry_basis_sign is not None
                                     and (basis > 0) != (cfg._entry_basis_sign > 0)
                                     and abs(basis) >= cfg.exit_threshold)
                    if unlock or reversed_sign:
                        lp, lf = _close_leg(long_pos, Lc, cfg.long_exchange, long_entry_bar, ts, capital)
                        sp, sf = _close_leg(short_pos, Sc, cfg.short_exchange, short_entry_bar, ts, capital)
                        leg_pnl = lp + sp
                        capital += leg_pnl
                        trade = Trade(
                            entry_time=long_entry_bar or ts,
                            entry_price=long_pos.entry_price,
                            size=abs(long_pos.size),
                            exit_time=ts,
                            exit_price=Sc,
                            pnl=leg_pnl,
                            pnl_pct=leg_pnl / (cfg.initial_capital * cfg.allocation_pct) * 100,
                            funding_paid=lf + sf,
                        )
                        trades.append(trade)
                        long_pos = short_pos = None
                        long_entry_bar = short_entry_bar = None
                        in_trade = False
                        cfg._entry_basis_sign = None
                else:  # basis mode
                    if abs(basis) <= cfg.exit_threshold:
                        lp, lf = _close_leg(long_pos, Lc, cfg.long_exchange, long_entry_bar, ts, capital)
                        sp, sf = _close_leg(short_pos, Sc, cfg.short_exchange, short_entry_bar, ts, capital)
                        leg_pnl = lp + sp
                        capital += leg_pnl
                        trade = Trade(
                            entry_time=long_entry_bar or ts,
                            entry_price=long_pos.entry_price,
                            size=abs(long_pos.size),
                            exit_time=ts,
                            exit_price=Sc,
                            pnl=leg_pnl,
                            pnl_pct=leg_pnl / (cfg.initial_capital * cfg.allocation_pct) * 100,
                            funding_paid=lf + sf,
                        )
                        trades.append(trade)
                        long_pos = short_pos = None
                        long_entry_bar = short_entry_bar = None
                        in_trade = False

            # MTM
            mtm = 0.0
            if long_pos is not None:
                long_pos.current_price = Lc
                mtm += long_pos.size * (Lc - long_pos.entry_price)
            if short_pos is not None:
                short_pos.current_price = Sc
                mtm += short_pos.size * (Sc - short_pos.entry_price)
            equity = capital + mtm
            equity_curve.append(equity)
            timestamps.append(ts)
            peak = max(equity_curve)
            dd = (peak - equity) / peak * 100 if peak else 0.0
            drawdown_curve.append(dd)

        return self._metrics(trades, equity_curve, drawdown_curve, timestamps)

    def _metrics(self, trades, equity, dd, timestamps) -> ArbResult:
        winners = [t for t in trades if t.pnl is not None and t.pnl > 0]
        losers = [t for t in trades if t.pnl is not None and t.pnl <= 0]
        total_pnl = sum(t.pnl for t in trades if t.pnl is not None)
        final_equity = equity[-1] if equity else self.cfg.initial_capital
        returns = np.diff(equity) / np.array(equity[:-1]) if len(equity) > 1 else np.array([])
        returns = returns[~np.isnan(returns) & ~np.isinf(returns)]
        return ArbResult(
            total_trades=len(trades),
            winning_trades=len(winners),
            losing_trades=len(losers),
            win_rate=len(winners) / len(trades) * 100 if trades else 0,
            total_pnl=total_pnl,
            total_return=total_pnl,
            total_return_pct=(final_equity - self.cfg.initial_capital) / self.cfg.initial_capital * 100,
            max_drawdown=max(dd) if dd else 0.0,
            max_drawdown_pct=max(dd) if dd else 0.0,
            sharpe_ratio=self._sharpe(returns),
            sortino_ratio=self._sortino(returns),
            profit_factor=abs(sum(t.pnl for t in winners) / sum(t.pnl for t in losers)) if losers else 0.0,
            avg_trade=total_pnl / len(trades) if trades else 0,
            avg_winner=sum(t.pnl for t in winners) / len(winners) if winners else 0,
            avg_loser=sum(t.pnl for t in losers) / len(losers) if losers else 0,
            trades=trades,
            equity_curve=equity,
            drawdown_curve=dd,
            timestamps=timestamps,
        )

    @staticmethod
    def _sharpe(returns, rf: float = 0.02) -> float:
        if len(returns) == 0 or np.std(returns) == 0:
            return 0.0
        excess = returns - rf / 252
        return float(np.mean(excess) / np.std(excess) * np.sqrt(252))

    @staticmethod
    def _sortino(returns, rf: float = 0.02) -> float:
        if len(returns) == 0:
            return 0.0
        excess = returns - rf / 252
        downside = returns[returns < 0]
        if len(downside) == 0:
            return 0.0
        return float(np.mean(excess) / np.std(downside) * np.sqrt(252))
