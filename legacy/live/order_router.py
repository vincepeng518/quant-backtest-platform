"""
Live Trading: 訂單路由

把 OrderEvent 送到真實交易所（CCXT）。

架構：
OrderEvent → OrderRouter → CCXT.create_order → 回傳 OrderID
                              ↓
                       WebSocket 監聽成交
                              ↓
                       FillEvent → 餵回 Engine
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, Optional, Callable
from dataclasses import dataclass, field
import pandas as pd

from events import OrderEvent, OrderSide, OrderType, FillEvent

logger = logging.getLogger(__name__)


@dataclass
class OrderTracking:
    """追蹤中的訂單"""
    order_id: str = ""
    order_event: OrderEvent = None
    submitted_at: float = 0.0
    filled: bool = False
    fill_price: float = 0.0
    fill_quantity: float = 0.0
    symbol: str = ""   # 每單獨立記標的, 避免併發共用 _last_symbol 查錯


class CCXTOrderRouter:
    """
    CCXT 訂單路由器

    接收 OrderEvent，送給交易所，回傳 FillEvent。
    """

    def __init__(
        self,
        exchange_id: str = "binance",
        api_key: str = "",
        secret: str = "",
        sandbox: bool = True,  # 預設 testnet
    ):
        self.exchange_id = exchange_id
        self.api_key = api_key
        self.secret = secret
        self.sandbox = sandbox
        self._exchange = None
        self._pending: Dict[str, OrderTracking] = {}
        self._on_fill: Optional[Callable[[FillEvent], None]] = None
        self._dry_run = not (api_key and secret)  # 沒 API key 時 dry run

    def set_fill_callback(self, callback: Callable[[FillEvent], None]) -> None:
        """設定成交 callback（用於把 FillEvent 餵回 Engine）"""
        self._on_fill = callback

    async def _ensure_exchange(self):
        """lazy init exchange"""
        if self._exchange is None:
            try:
                import ccxt.async_support as ccxt
            except ImportError:
                raise ImportError("請先 pip install ccxt")

            exchange_class = getattr(ccxt, self.exchange_id)
            config = {
                "enableRateLimit": True,
            }
            if self.api_key and self.secret:
                config["apiKey"] = self.api_key
                config["secret"] = self.secret
            self._exchange = exchange_class(config)
            if self.sandbox:
                self._exchange.set_sandbox_mode(True)

    async def submit_order(self, order: OrderEvent, symbol: str) -> str:
        """
        送出訂單到交易所

        Returns:
            order_id
        """
        await self._ensure_exchange()

        if self._dry_run:
            return await self._submit_dry_run(order, symbol)

        # 真實下單
        side = "buy" if order.side == OrderSide.BUY else "sell"
        order_type = "market" if order.order_type == OrderType.MARKET else "limit"
        params = {}

        if order.is_close:
            params["reduceOnly"] = True  # 確保是平倉單

        import uuid as _uuid
        params.setdefault("clientOrderId", f"hm-{_uuid.uuid4().hex[:12]}")  # 冪等
        try:
            result = await self._exchange.create_order(
                symbol=symbol,
                type=order_type,
                side=side,
                amount=order.quantity,
                price=order.price,
                params=params,
            )
            order_id = result["id"]
            logger.info(f"訂單送出: {side} {order.quantity} {symbol} @ {order.price} → {order_id}")

            # 追蹤 (存正確 symbol, 不用共用 _last_symbol)
            self._pending[order_id] = OrderTracking(
                order_id=order_id,
                order_event=order,
                submitted_at=time.time(),
                symbol=symbol,
            )
            return order_id

        except Exception as e:
            logger.exception(f"下單失敗: {e}")
            raise

    async def _submit_dry_run(self, order: OrderEvent, symbol: str) -> str:
        """
        Dry-run 模式：不實際下單，立即假裝成交

        用於：
        - 測試
        - paper trading
        - 沙盒環境
        """
        import uuid
        order_id = f"dry_{uuid.uuid4().hex[:8]}"
        side_str = "BUY" if order.side == OrderSide.BUY else "SELL"
        logger.info(f"[DRY-RUN] {side_str} {order.quantity} {symbol} @ {order.price}")

        # 立即模擬成交
        fill = FillEvent(
            timestamp=order.timestamp,
            side=order.side,
            quantity=order.quantity,
            price=order.price or 0,
            commission=0,
            slippage=0,
            order_id=order_id,
            is_close=order.is_close,
        )
        if self._on_fill:
            self._on_fill(fill)

        return order_id

    async def poll_pending_orders(self) -> None:
        """定期查詢未成交訂單狀態"""
        if not self._pending or self._dry_run:
            return

        await self._ensure_exchange()
        for order_id, tracking in list(self._pending.items()):
            if tracking.filled:
                continue
            try:
                status = await self._exchange.fetch_order(order_id, tracking.symbol)
                if status["status"] == "closed":
                    # 已成交
                    tracking.filled = True
                    tracking.fill_price = status["average"] or status["price"]
                    tracking.fill_quantity = status["filled"]
                    fill_ts = status.get("timestamp")
                    fill = FillEvent(
                        timestamp=(pd.Timestamp(fill_ts, unit="ms", tz="UTC").to_pydatetime() if fill_ts else pd.Timestamp.now(tz="UTC").to_pydatetime()),
                        side=tracking.order_event.side,
                        quantity=tracking.fill_quantity,
                        price=tracking.fill_price,
                        commission=status.get("fee", {}).get("cost", 0),
                        slippage=0,
                        order_id=order_id,
                        is_close=tracking.order_event.is_close,
                    )
                    if self._on_fill:
                        self._on_fill(fill)
                    del self._pending[order_id]
            except Exception as e:
                logger.warning(f"查詢訂單 {order_id} 失敗, 保留下輪重試: {e}")  # 不移除, 避免永久卡住

    async def close(self) -> None:
        if self._exchange:
            await self._exchange.close()
