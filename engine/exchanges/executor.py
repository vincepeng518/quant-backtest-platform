from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from engine.exchanges.registry import EXCHANGE_REGISTRY, get_exchange_spec

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    ok: bool
    exchange: str
    symbol: str
    side: str
    order_type: str
    price: Optional[float]
    qty: float
    order_id: Optional[str] = None
    raw: Optional[dict] = None
    error: Optional[str] = None
    paper: bool = False


class ExchangeExecutor:
    """Real/simulated order execution across multiple exchanges via ccxt.

    mode="paper" (default): validates the order against ccxt market data and
    returns a simulated fill at mid ± slippage. NO real money moves.
    mode="live": places the actual order through ccxt (requires API keys in
    the environment / ccxt config). Use with extreme caution.

    The backtest path uses ExchangeModel (engine/exchange.py) for simulation;
    this class is for live/paper trading and for comparing exchange fees in
    the UI (multi-exchange execution layer).
    """

    def __init__(self, exchanges: Optional[list[str]] = None, mode: str = "paper") -> None:
        self.exchanges = [e.lower() for e in (exchanges or ["bingx"])]
        self.mode = mode  # "paper" | "live"
        self._ccxt: dict[str, Any] = {}

    def _get_ccxt(self, name: str):
        if name in self._ccxt:
            return self._ccxt[name]
        import ccxt

        ex = getattr(ccxt, name)()
        ex.timeout = 20_000
        self._ccxt[name] = ex
        return ex

    async def place_order(
        self,
        symbol: str,
        side: str,            # "buy" | "sell"
        qty: float,
        order_type: str = "market",
        price: Optional[float] = None,
        exchange: str = "bingx",
    ) -> OrderResult:
        if exchange not in self.exchanges:
            return OrderResult(False, exchange, symbol, side, order_type, price, qty, error="exchange not in allowed list")
        spec = get_exchange_spec(exchange)
        if spec is None:
            return OrderResult(False, exchange, symbol, side, order_type, price, qty, error="unknown exchange")

        if self.mode == "paper":
            # paper: fetch last price, simulate fill at mid ± slippage
            try:
                ex = self._get_ccxt(exchange)
                ticker = await asyncio.to_thread(ex.fetch_ticker, symbol)
                last = float(ticker.get("last") or ticker.get("close") or 0.0)
                slip = spec.book_base_slippage
                direction = 1 if side == "buy" else -1
                fill = last * (1 + direction * slip)
                fee_rate = spec.maker_fee if order_type == "limit" else spec.taker_fee
                return OrderResult(
                    ok=True, exchange=exchange, symbol=symbol, side=side,
                    order_type=order_type, price=fill, qty=qty,
                    order_id=f"paper-{exchange}-{side}-{int(asyncio.get_event_loop().time())}",
                    raw={"last": last, "fee_rate": fee_rate}, paper=True,
                )
            except Exception as e:
                return OrderResult(False, exchange, symbol, side, order_type, price, qty, error=f"paper fetch failed: {e}")

        # live mode
        try:
            ex = self._get_ccxt(exchange)
            if order_type == "limit" and price is not None:
                raw = await asyncio.to_thread(ex.create_limit_order, symbol, side, qty, price)
            else:
                raw = await asyncio.to_thread(ex.create_market_order, symbol, side, qty)
            return OrderResult(
                ok=True, exchange=exchange, symbol=symbol, side=side,
                order_type=order_type, price=price, qty=qty,
                order_id=str(raw.get("id")), raw=raw, paper=False,
            )
        except Exception as e:
            logger.exception("live order failed on %s", exchange)
            return OrderResult(False, exchange, symbol, side, order_type, price, qty, error=f"live order failed: {e}")

    async def compare_fees(self, symbol: str, qty: float, side: str = "buy") -> list[dict]:
        """Compare fill cost across all configured exchanges (paper-quoted)."""
        out = []
        for ex in self.exchanges:
            spec = get_exchange_spec(ex)
            if spec is None:
                continue
            res = await self.place_order(symbol, side, qty, "market", exchange=ex)
            if res.ok:
                fee_rate = spec.taker_fee
                cost = (res.price or 0.0) * qty * fee_rate
                out.append({
                    "exchange": ex,
                    "name": spec.name,
                    "fill_price": res.price,
                    "fee_rate": fee_rate,
                    "fee_cost": cost,
                    "latency_ms": spec.latency_ms,
                    "paper": True,
                })
        return out
