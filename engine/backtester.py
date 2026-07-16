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
    direction: str = "long"  # long / short, derived from position.size sign
    exit_reason: str = ""  # signal / liquidation / end
    holding_bars: int = 0  # exit_bar_index - entry_bar_index


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
    largest_loss: float = 0.0
    largest_loss_pct: float = 0.0
    largest_win: float = 0.0
    avg_trade: float = 0.0
    avg_winner: float = 0.0
    avg_loser: float = 0.0
    win_loss_ratio: float = 0.0  # avg_win / |avg_loss| (payoff ratio)
    expectancy: float = 0.0  # per-trade expected PnL
    annual_return_pct: float = 0.0  # CAGR
    avg_holding_bars: float = 0.0
    trade_freq: float = 0.0  # trades per day
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    drawdown_curve: list[float] = field(default_factory=list)
    buy_hold_curve: list[float] = field(default_factory=list)
    timestamps: list[pd.Timestamp] = field(default_factory=list)
    position_status: list[dict] = field(default_factory=list)


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
        market_engine: "Optional[Any]" = None,
    ) -> None:
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.funding = funding
        self.perp = perp
        self.leverage = leverage
        self.exchange = exchange
        self.force_limit = force_limit
        self.market_engine = market_engine
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
        buy_hold_curve: list[float] = [capital]
        timestamps: list[Any] = [self.data.iloc[0].timestamp]
        trades: list[Trade] = []
        entry_bar: Optional[pd.Timestamp] = None
        entry_bar_index: Optional[int] = None

        # Latency queue: pending (signal_bar_index, bar, signal) entries executed
        # once the current bar index has advanced fill_delay_bars() past the signal.
        pending_signals: list[tuple[int, Any, Any]] = []
        delay = self.exchange.fill_delay_bars() if self.exchange is not None else 0

        def _fee_for(order_type: str, is_maker: bool, notional: float = 0.0, action: str = "") -> float:
            if self.market_engine is not None:
                return self.market_engine.commission(notional, is_open=(action in ("buy", "sell")))
            if self.exchange is not None:
                rate = self.exchange.fee_for(order_type, is_maker)
                return notional * rate
            return self.commission

        def _slippage_for(capital_to_risk: float, price: float, direction: int) -> float:
            if self.market_engine is not None:
                return self.market_engine.slippage_factor(direction) - 1.0
            if self.exchange is not None:
                qty = abs(capital_to_risk / price) if price else 0.0
                return self.exchange.slippage_for(depth=1000.0, qty=qty)
            return self.slippage

        def _size_for(capital: float, price: float) -> float:
            if self.market_engine is not None:
                return self.market_engine.position_size(capital, price, self.leverage)
            return (capital * self.leverage) / price if self.perp is not None else capital / price

        def _execute(sig: Any, current_bar: Any, current_bar_index: int) -> None:
            nonlocal capital, position, entry_bar, entry_bar_index
            order_type = "limit" if self.force_limit else getattr(sig, "order_type", "market")
            is_maker = self.exchange.decide_maker(order_type) if self.exchange is not None else (order_type == "limit")
            direction = 1 if sig.action == "buy" else -1

            if sig.action in ("buy", "sell") and position is None:
                price = sig.price or current_bar.close
                # Limit orders may not fill (fill probability model)
                if order_type == "limit" and self.market_engine is not None:
                    if not self.market_engine.exec_model.will_fill("limit"):
                        return
                if self.market_engine is not None:
                    fill_price = self.market_engine.exec_model.fill_price(price, sig.action, is_entry=True)
                else:
                    slip = _slippage_for(capital, price, direction)
                    fill_price = price * (1 + slip * direction)
                notional = capital * (self.leverage if self.perp is not None else 1.0)
                fee = _fee_for(order_type, is_maker, notional if self.market_engine is not None else capital, action=sig.action)
                size = _size_for(capital, fill_price)
                size = size if direction > 0 else -size
                position = Position(size=size, entry_price=fill_price, current_price=fill_price)
                capital -= fee
                entry_bar = current_bar.timestamp
                entry_bar_index = current_bar_index

            elif sig.action in ("close",) and position is not None:
                if order_type == "limit" and self.market_engine is not None:
                    if not self.market_engine.exec_model.will_fill("limit"):
                        return
                if self.market_engine is not None:
                    exit_price = self.market_engine.exec_model.fill_price(
                        current_bar.close, "sell" if position.size > 0 else "buy", is_entry=False
                    )
                else:
                    slip = _slippage_for(capital, current_bar.close, -1 if position.size > 0 else 1)
                    exit_price = current_bar.close * (1 + slip * (-1 if position.size > 0 else 1))
                pnl = position.size * (exit_price - position.entry_price)
                fee = _fee_for(order_type, is_maker, abs(position.size) * position.entry_price if self.market_engine is not None else capital, action="close")
                pnl -= fee
                funding_paid = 0.0
                if self.funding is not None:
                    notional = abs(position.size) * position.entry_price
                    side = 1 if position.size > 0 else -1
                    funding_frac = self.funding.accrued(entry_bar, current_bar.timestamp, side)
                    funding_paid = notional * funding_frac
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
                    direction="long" if position.size > 0 else "short",
                    exit_reason="signal",
                    holding_bars=(current_bar_index - entry_bar_index) if entry_bar_index is not None else 0,
                )
                trades.append(trade)
                capital += pnl
                position = None
                entry_bar = None
                entry_bar_index = None

        for i, (_, row) in enumerate(self.data.iterrows()):
            bar = Bar(
                timestamp=row["timestamp"],
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                metadata=dict(row["metadata"]) if "metadata" in row and isinstance(row.get("metadata"), dict) else None,
            )

            signal = self.strategy.next(bar)
            if signal:
                self.events.emit("signal", signal)
                # Market session gate (equity/forex: skip if closed)
                if self.market_engine is not None and not self.market_engine.can_execute(bar.timestamp):
                    signal = None
                if signal is not None:
                    if delay > 0:
                        pending_signals.append((i, bar, signal))
                    else:
                        _execute(signal, bar, i)

            # Drain latency queue: execute signals that are due this bar.
            if delay > 0:
                still_pending: list[tuple[int, Any, Any]] = []
                for sig_i, sig_bar, sig in pending_signals:
                    if i >= sig_i + delay:
                        _execute(sig, bar, i)
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

            # Market-engine per-bar hooks (funding / swap / liquidation)
            if self.market_engine is not None and position is not None:
                hook = self.market_engine.on_bar(bar, bar.timestamp, None)
                if hook.get("funding_fee"):
                    capital -= hook["funding_fee"]
                if hook.get("swap_fee"):
                    capital -= hook["swap_fee"]
                if hook.get("liquidated"):
                    slip = self.market_engine.slippage_factor(-1 if position.size > 0 else 1) - 1.0
                    exit_price = bar.close * (1 + slip * (-1 if position.size > 0 else 1))
                    pnl = position.size * (exit_price - position.entry_price)
                    fee = self.market_engine.commission(abs(position.size) * position.entry_price, is_open=False)
                    pnl -= fee
                    trade = Trade(entry_time=entry_bar or bar.timestamp, entry_price=position.entry_price,
                                  size=abs(position.size), exit_time=bar.timestamp, exit_price=exit_price,
                                  pnl=pnl, pnl_pct=pnl / capital * 100, funding_paid=hook.get("funding_fee", 0.0),
                                  liquidated=True, direction="long" if position.size > 0 else "short",
                                  exit_reason="liquidation",
                                  holding_bars=(i - entry_bar_index) if entry_bar_index is not None else 0)
                    trades.append(trade)
                    capital += pnl
                    position = None
                    entry_bar = None
                    entry_bar_index = None
            # Legacy perp liquidation path (when no market_engine, perp set directly)
            elif self.perp is not None and position is not None:
                side = 1 if position.size > 0 else -1
                mark = bar.low if side > 0 else bar.high
                if self.perp.check_liquidation(mark, position.entry_price, position.size, self.leverage,
                                              notional=abs(position.size) * position.entry_price):
                    liq_price = mark
                    exit_price = liq_price
                    pnl = position.size * (exit_price - position.entry_price)
                    pnl -= capital * self.commission
                    # funding (if T2 wiring present, also accrue on forced close)
                    trade = Trade(entry_time=entry_bar or bar.timestamp, entry_price=position.entry_price,
                                  size=abs(position.size), exit_time=bar.timestamp, exit_price=exit_price,
                                  pnl=pnl, pnl_pct=pnl / capital * 100, funding_paid=getattr(self, '_last_funding', 0.0), liquidated=True,
                                  direction="long" if position.size > 0 else "short",
                                  exit_reason="liquidation",
                                  holding_bars=(i - entry_bar_index) if entry_bar_index is not None else 0)
                    trades.append(trade)
                    capital += pnl
                    position = None
                    entry_bar = None
                    entry_bar_index = None

            current_equity = capital + (position.pnl if position else 0)
            equity_curve.append(current_equity)
            peak = max(equity_curve)
            dd = (peak - current_equity) / peak * 100
            drawdown_curve.append(dd)
            timestamps.append(bar.timestamp)
            # Buy & hold baseline: hold the asset from bar 0, scaled to initial capital
            if len(buy_hold_curve) == 1:
                buy_hold_curve.append(capital)
            else:
                base_close = self.data.iloc[0].close
                buy_hold_curve.append(capital * (bar.close / base_close))

        return self._calculate_metrics(trades, equity_curve, drawdown_curve, buy_hold_curve, timestamps)

    def _calculate_metrics(
        self, trades: list[Trade], equity: list[float], dd: list[float],
        buy_hold_curve: list[float] | None = None, timestamps: list[Any] | None = None,
    ) -> BacktestResult:
        winners = [t for t in trades if t.pnl is not None and t.pnl > 0]
        losers = [t for t in trades if t.pnl is not None and t.pnl <= 0]
        total_pnl = sum(t.pnl for t in trades if t.pnl is not None)
        final_equity = equity[-1]

        losses = [t.pnl for t in losers]
        largest_loss = min(losses) if losses else 0.0
        # TV "Largest Losing Trade": single biggest loss (absolute pnl).
        largest_loss_pct = min(
            [t.pnl_pct for t in losers if t.pnl_pct is not None], default=0.0
        )
        wins = [t.pnl for t in winners if t.pnl is not None]
        largest_win = max(wins) if wins else 0.0

        returns = np.diff(equity) / np.array(equity[:-1])
        returns = returns[~np.isnan(returns) & ~np.isinf(returns)]
        # TV convention: Sharpe/Sortino computed from DAILY returns, annualized
        # via sqrt(252). Resample equity to last-per-day; fall back to per-bar
        # returns (annualized at 252) only for very short tests.
        daily_returns = self._daily_returns(equity, timestamps or [])
        sr_returns = daily_returns if len(daily_returns) >= 2 else returns

        # --- PnL% fix: TV口径 = pnl / 持仓名义价值(size*entry_price), NOT /total capital ---
        for t in trades:
            notional = (t.size * t.entry_price) if t.size and t.entry_price else 0.0
            t.pnl_pct = (t.pnl / notional * 100) if (notional and t.pnl is not None) else 0.0

        # --- TV-extended metrics ---
        # Annualized return: CAGR from total_return_pct over the test period.
        annual_return_pct = 0.0
        days = 0
        if timestamps and len(timestamps) >= 2:
            days = (pd.Timestamp(timestamps[-1]) - pd.Timestamp(timestamps[0])).days
            if days > 0 and final_equity > 0:
                years = days / 365.0
                annual_return_pct = ((final_equity / self.initial_capital) ** (1 / years) - 1) * 100
        # Calmar = annualized return / max drawdown (%).
        calmar = (annual_return_pct / max(dd)) if max(dd) > 0 else 0.0
        # Avg win/loss ratio (payoff ratio).
        avg_win = sum(t.pnl for t in winners) / len(winners) if winners else 0.0
        avg_loss = sum(t.pnl for t in losers) / len(losers) if losers else 0.0
        win_loss_ratio = (avg_win / abs(avg_loss)) if avg_loss != 0 else 0.0
        # Expectancy = win_rate*avg_win - loss_rate*avg_loss (per trade expected PnL).
        wr = (len(winners) / len(trades)) if trades else 0.0
        expectancy = (wr * avg_win - (1 - wr) * abs(avg_loss)) if trades else 0.0
        # Avg holding period (bars) + trade frequency (trades/day).
        avg_holding_bars = (
            sum(t.holding_bars for t in trades) / len(trades)
        ) if trades else 0.0
        trade_freq = (len(trades) / days) if days > 0 else 0.0

        position_status = self._build_position_status(trades)

        return BacktestResult(
            total_trades=len(trades),
            winning_trades=len(winners),
            losing_trades=len(losers),
            win_rate=len(winners) / len(trades) * 100 if trades else 0,
            total_pnl=total_pnl,
            total_return=total_pnl,
            total_return_pct=(final_equity - self.initial_capital) / self.initial_capital * 100,
            # TV convention:
            #   max_drawdown      = peak-to-trough DOLLAR loss
            #   max_drawdown_pct  = same decline as % of the peak equity
            max_drawdown=(self.initial_capital * max(dd) / 100) if self.initial_capital else max(dd),
            max_drawdown_pct=max(dd),
            sharpe_ratio=self._sharpe(sr_returns),
            sortino_ratio=self._sortino(sr_returns),
            profit_factor=abs(sum(t.pnl for t in winners) / sum(t.pnl for t in losers)) if losers else 0.0,
            largest_loss=largest_loss,
            largest_loss_pct=largest_loss_pct,
            largest_win=largest_win,
            avg_trade=total_pnl / len(trades) if trades else 0,
            avg_winner=avg_win,
            avg_loser=avg_loss,
            win_loss_ratio=win_loss_ratio,
            expectancy=expectancy,
            annual_return_pct=annual_return_pct,
            calmar_ratio=calmar,
            avg_holding_bars=avg_holding_bars,
            trade_freq=trade_freq,
            trades=trades,
            equity_curve=equity,
            drawdown_curve=dd,
            buy_hold_curve=buy_hold_curve or [],
            timestamps=timestamps or [],
            position_status=position_status,
        )

    @staticmethod
    def _to_unix(value: Any) -> Optional[int]:
        """Convert a timestamp (pd.Timestamp / str / int / float) to unix seconds."""
        if value is None:
            return None
        try:
            if isinstance(value, (int, float)):
                return int(value)
            ts = pd.Timestamp(value)
            if ts is pd.NaT:
                return None
            return int(ts.timestamp())
        except Exception:
            return None

    @staticmethod
    def _build_position_status(trades: list[Trade]) -> list[dict]:
        """Derive a sorted list of {time, state} segments from trades.

        For each trade we emit a segment marking the entry with the trade's
        direction (long/short) and the exit with 'flat'. Segments are sorted
        by time so the frontend can render colored blocks (long=green,
        short=red, flat=transparent) aligned to the X axis.
        """
        segments: list[dict] = []
        for t in trades:
            entry_ts = Backtester._to_unix(t.entry_time)
            if entry_ts is not None:
                segments.append({"time": entry_ts, "state": t.direction})
            exit_ts = Backtester._to_unix(t.exit_time)
            if exit_ts is not None:
                segments.append({"time": exit_ts, "state": "flat"})
        segments.sort(key=lambda seg: seg["time"])
        return segments

    @staticmethod
    def _daily_returns(equity: list[float], timestamps: list[Any]) -> np.ndarray:
        """Collapse per-bar equity into end-of-day returns (TV Sharpe/Sortino basis).

        If we can't align to calendar days (no/short timestamps), returns empty
        and the caller falls back to per-bar returns.
        """
        if not timestamps or len(equity) < 2:
            return np.array([])
        try:
            import pandas as pd
            ts = pd.to_datetime(timestamps)
            eq = np.asarray(equity, dtype=float)
            if len(ts) != len(eq):
                return np.array([])
            s = pd.Series(eq, index=ts).sort_index()
            daily = s.groupby([pd.Timestamp(d).date() for d in s.index]).last()
            if len(daily) < 2:
                return np.array([])
            dv = daily.to_numpy(dtype=float)
            r = dv[1:] / dv[:-1] - 1.0
            return r[~np.isnan(r) & ~np.isinf(r)]
        except Exception:
            return np.array([])

    @staticmethod
    def _sharpe(returns: np.ndarray, rf: float = 0.02) -> float:
        # Assumes `returns` are DAILY returns; annualize via sqrt(252).
        if len(returns) == 0 or np.std(returns) == 0:
            return 0.0
        excess = returns - rf / 252
        return float(np.mean(excess) / np.std(excess) * np.sqrt(252))

    @staticmethod
    def _sortino(returns: np.ndarray, rf: float = 0.02) -> float:
        # Assumes `returns` are DAILY returns; annualize via sqrt(252).
        if len(returns) == 0:
            return 0.0
        excess = returns - rf / 252
        downside = returns[returns < 0]
        if len(downside) == 0 or np.std(downside) == 0:
            return 0.0
        return float(np.mean(excess) / np.std(downside) * np.sqrt(252))