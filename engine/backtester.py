from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

from engine.events import EventEmitter
from strategies.base import Bar, Position, Signal, StrategyBase

try:
    from engine.funding import FundingModel
except Exception:  # pragma: no cover - keep default path working if model missing
    FundingModel = None  # type: ignore[assignment]

try:
    from engine.perpetual import PerpSimulator
except Exception:  # pragma: no cover - keep default path working if model missing
    PerpSimulator = None  # type: ignore[assignment]

try:
    from engine.exchange import ExchangeModel
except Exception:  # pragma: no cover - keep default path working if model missing
    ExchangeModel = None  # type: ignore[assignment]


@dataclass
class Trade:
    entry_time: pd.Timestamp
    entry_price: float
    size: float
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    funding_paid: float = 0.0
    liquidated: bool = False


@dataclass
class BacktestResult:
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
    calmar_ratio: float = 0.0
    avg_trade: float = 0.0
    avg_winner: float = 0.0
    avg_loser: float = 0.0
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    drawdown_curve: list[float] = field(default_factory=list)
    timestamps: list[pd.Timestamp] = field(default_factory=list)


class Backtester:
    def __init__(
        self,
        initial_capital: float = 100_000,
        commission: float = 0.001,
        slippage: float = 0.0005,
        funding: "Optional[FundingModel]" = None,
        perp: "Optional[PerpSimulator]" = None,
        leverage: float = 1.0,
        exchange: "Optional[ExchangeModel]" = None,
        force_limit: bool = False,
    ) -> None:
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.funding = funding
        self.perp = perp
        self.leverage = leverage
        self.exchange = exchange
        self.force_limit = force_limit
        self.strategy: Optional[StrategyBase] = None
        self.data: Optional[pd.DataFrame] = None
        self.events = EventEmitter()

    def set_strategy(self, strategy: StrategyBase) -> None:
        self.strategy = strategy

    def set_data(self, data: pd.DataFrame) -> None:
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        if not required.issubset(data.columns):
            raise ValueError(f"Data must contain columns: {required}")
        self.data = data.sort_values("timestamp").reset_index(drop=True)

    def run(self) -> BacktestResult:
        if self.strategy is None or self.data is None:
            raise ValueError("Strategy and data must be set")

        capital = self.initial_capital
        position: Optional[Position] = None
        equity_curve: list[float] = [capital]
        drawdown_curve: list[float] = [0.0]
        trades: list[Trade] = []
        entry_bar: Optional[pd.Timestamp] = None

        # Latency queue: pending (signal_bar_index, bar, signal) entries executed
        # once the current bar index has advanced fill_delay_bars() past the signal.
        pending_signals: list[tuple[int, Any, Any]] = []
        delay = self.exchange.fill_delay_bars() if self.exchange is not None else 0

        def _fee_for(order_type: str, is_maker: bool) -> float:
            if self.exchange is not None:
                return self.exchange.fee_for(order_type, is_maker)
            return self.commission

        def _slippage_for(capital_to_risk: float, price: float) -> float:
            if self.exchange is not None:
                qty = abs(capital_to_risk / price) if price else 0.0
                return self.exchange.slippage_for(depth=1000.0, qty=qty)
            return self.slippage

        def _execute(sig: Any, current_bar: Any) -> None:
            nonlocal capital, position, entry_bar
            order_type = "limit" if self.force_limit else getattr(sig, "order_type", "market")
            # A limit order rests on the book; whether it fills as maker is decided
            # by the exchange model (maker_probability). Market orders are taker.
            is_maker = self.exchange.decide_maker(order_type) if self.exchange is not None else (order_type == "limit")
            fee = _fee_for(order_type, is_maker)
            slip = _slippage_for(capital, current_bar.close)

            if sig.action == "buy" and position is None:
                price = sig.price * (1 + slip) if sig.price else current_bar.close * (1 + slip)
                cost = capital * fee
                size = (capital * self.leverage) / price if self.perp is not None else capital / price
                position = Position(size=size, entry_price=price, current_price=price)
                capital -= cost
                entry_bar = current_bar.timestamp

            elif sig.action == "sell" and position is None:
                price = sig.price * (1 - slip) if sig.price else current_bar.close * (1 - slip)
                cost = capital * fee
                size = -(capital * self.leverage) / price if self.perp is not None else -capital / price
                position = Position(size=size, entry_price=price, current_price=price)
                capital -= cost
                entry_bar = current_bar.timestamp

            elif sig.action in ("close",) and position is not None:
                exit_price = (
                    current_bar.close * (1 - slip if position.size > 0 else 1 + slip)
                )
                pnl = position.size * (exit_price - position.entry_price)
                pnl -= capital * fee
                funding_paid = 0.0
                if self.funding is not None:
                    notional = abs(position.size) * position.entry_price
                    side = 1 if position.size > 0 else -1
                    funding_frac = self.funding.accrued(entry_bar, current_bar.timestamp, side)
                    funding_paid = notional * funding_frac  # long positive => cost
                    pnl -= funding_paid
                trade = Trade(
                    entry_time=entry_bar or current_bar.timestamp,
                    entry_price=position.entry_price,
                    size=abs(position.size),
                    exit_time=current_bar.timestamp,
                    exit_price=exit_price,
                    pnl=pnl,
                    pnl_pct=pnl / capital * 100,
                    funding_paid=funding_paid,
                )
                trades.append(trade)
                capital += pnl
                position = None
                entry_bar = None

        for i, (_, row) in enumerate(self.data.iterrows()):
            bar = Bar(
                timestamp=row["timestamp"],
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
            )

            signal = self.strategy.next(bar)
            if signal:
                self.events.emit("signal", signal)
                if delay > 0:
                    # Buffer the signal; it executes fill_delay_bars() later.
                    pending_signals.append((i, bar, signal))
                else:
                    _execute(signal, bar)

            # Drain latency queue: execute signals that are due this bar.
            if delay > 0:
                still_pending: list[tuple[int, Any, Any]] = []
                for sig_i, sig_bar, sig in pending_signals:
                    if i >= sig_i + delay:
                        _execute(sig, bar)
                    else:
                        still_pending.append((sig_i, sig_bar, sig))
                pending_signals = still_pending

            # Update position MTM
            if position is not None:
                position.current_price = bar.close
                position.pnl = position.size * (bar.close - position.entry_price)
                position.pnl_pct = position.pnl / capital * 100
            # Sync position back to strategy so strategies can read their own book
            self.strategy.position = position

            # Liquidation check (perp markets only)
            if self.perp is not None and position is not None:
                side = 1 if position.size > 0 else -1
                # worst-case wick against the position
                mark = bar.low if side > 0 else bar.high
                if self.perp.check_liquidation(mark, position.entry_price, position.size, self.leverage):
                    liq_price = mark
                    slip = self.slippage
                    exit_price = liq_price
                    pnl = position.size * (exit_price - position.entry_price)
                    pnl -= capital * self.commission
                    # funding (if T2 wiring present, also accrue on forced close)
                    trade = Trade(entry_time=entry_bar or bar.timestamp, entry_price=position.entry_price,
                                  size=abs(position.size), exit_time=bar.timestamp, exit_price=exit_price,
                                  pnl=pnl, pnl_pct=pnl / capital * 100, funding_paid=getattr(self, '_last_funding', 0.0), liquidated=True)
                    trades.append(trade)
                    capital += pnl
                    position = None
                    entry_bar = None

            current_equity = capital + (position.pnl if position else 0)
            equity_curve.append(current_equity)
            peak = max(equity_curve)
            dd = (peak - current_equity) / peak * 100
            drawdown_curve.append(dd)

        return self._calculate_metrics(trades, equity_curve, drawdown_curve)

    def _calculate_metrics(
        self, trades: list[Trade], equity: list[float], dd: list[float]
    ) -> BacktestResult:
        winners = [t for t in trades if t.pnl is not None and t.pnl > 0]
        losers = [t for t in trades if t.pnl is not None and t.pnl <= 0]
        total_pnl = sum(t.pnl for t in trades if t.pnl is not None)
        final_equity = equity[-1]

        returns = np.diff(equity) / np.array(equity[:-1])
        returns = returns[~np.isnan(returns) & ~np.isinf(returns)]

        return BacktestResult(
            total_trades=len(trades),
            winning_trades=len(winners),
            losing_trades=len(losers),
            win_rate=len(winners) / len(trades) * 100 if trades else 0,
            total_pnl=total_pnl,
            total_return_pct=(final_equity - self.initial_capital) / self.initial_capital * 100,
            total_return=total_pnl,
            max_drawdown=max(dd),
            max_drawdown_pct=max(dd),
            sharpe_ratio=self._sharpe(returns),
            sortino_ratio=self._sortino(returns),
            profit_factor=abs(sum(t.pnl for t in winners) / sum(t.pnl for t in losers)) if losers else 0.0,
            avg_trade=total_pnl / len(trades) if trades else 0,
            avg_winner=sum(t.pnl for t in winners) / len(winners) if winners else 0,
            avg_loser=sum(t.pnl for t in losers) / len(losers) if losers else 0,
            trades=trades,
            equity_curve=equity,
            drawdown_curve=dd,
        )

    @staticmethod
    def _sharpe(returns: np.ndarray, rf: float = 0.02) -> float:
        if len(returns) == 0 or np.std(returns) == 0:
            return 0.0
        excess = returns - rf / 252
        return float(np.mean(excess) / np.std(excess) * np.sqrt(252))

    @staticmethod
    def _sortino(returns: np.ndarray, rf: float = 0.02) -> float:
        if len(returns) == 0:
            return 0.0
        excess = returns - rf / 252
        downside = returns[returns < 0]
        if len(downside) == 0 or np.std(downside) == 0:
            return 0.0
        return float(np.mean(excess) / np.std(downside) * np.sqrt(252))