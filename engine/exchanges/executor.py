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
        import os

        ex = getattr(ccxt, name)()
        ex.timeout = 20_000
        # inject API keys for live mode exchanges that need them
        if name.lower() == "mexc":
            ak = os.getenv("MEXC_ACCESS_KEY")
            sk = os.getenv("MEXC_SECRET_KEY")
            if ak and sk:
                ex.apiKey = ak
                ex.secret = sk
        if name.lower() == "bingx":
            ak = os.getenv("BINGX_API_KEY")
            sk = os.getenv("BINGX_API_SECRET")
            if ak and sk:
                ex.apiKey = ak
                ex.secret = sk
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
        is_close: bool = False,
    ) -> OrderResult:
        if exchange not in self.exchanges:
            return OrderResult(False, exchange, symbol, side, order_type, price, qty, error="exchange not in allowed list")
        spec = get_exchange_spec(exchange)
        if spec is None:
            return OrderResult(False, exchange, symbol, side, order_type, price, qty, error="unknown exchange")

        if self.mode == "paper":
            # paper: fetch last price, simulate fill at volatility-aware slippage
            try:
                ex = self._get_ccxt(exchange)
                ticker = await asyncio.to_thread(ex.fetch_ticker, symbol)
                last = float(ticker.get("last") or ticker.get("close") or 0.0)
                # 滑點至少 book_base_slippage, 極端時用 0.2% 地板, 避免回測虛高
                slip = max(spec.book_base_slippage, abs(last * 0.002))
                direction = 1 if side == "buy" else -1
                fill = last * (1 + direction * slip)
                fee_rate = spec.maker_fee if order_type == "limit" else spec.taker_fee
                return OrderResult(
                    ok=True, exchange=exchange, symbol=symbol, side=side,
                    order_type=order_type, price=fill, qty=qty,
                    order_id=f"paper-{exchange}-{side}-{int(asyncio.get_event_loop().time())}",
                    raw={"last": last, "fee_rate": fee_rate, "slippage": slip}, paper=True,
                )
            except Exception as e:
                return OrderResult(False, exchange, symbol, side, order_type, price, qty, error=f"paper fetch failed: {e}")

        # live mode
        try:
            ex = self._get_ccxt(exchange)
            params = {}
            if is_close:
                params["reduceOnly"] = True   # 平倉單加防護, 避免反向開倉穿倉
            import uuid as _uuid
            params["clientOrderId"] = f"hm-{_uuid.uuid4().hex[:12]}"  # 冪等, 超時重送不重單
            if order_type == "limit" and price is not None:
                raw = await asyncio.to_thread(ex.create_order, symbol, "limit", side, qty, price, params)
            else:
                raw = await asyncio.to_thread(ex.create_order, symbol, "market", side, qty, None, params)
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
