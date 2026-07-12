"""
Live Trading: 持倉同步

定期從交易所查詢真實持倉，同步到本地 Portfolio。
處理網路斷線、訂單遺失等異常狀況。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional
from datetime import datetime, timezone

from engine import EventEngine
from events import FillEvent, OrderSide

logger = logging.getLogger(__name__)


class PositionSync:
    """
    持倉同步器

    每隔 N 秒查詢交易所真實持倉，與本地比對。
    若有差異（例如斷線時成交未通知）→ 同步本地狀態。
    """

    def __init__(
        self,
        engine: EventEngine,
        exchange_id: str = "binance",
        api_key: str = "",
        secret: str = "",
        symbol: str = "BTC/USDT",
        sync_interval: int = 30,
        sandbox: bool = True,
    ):
        self.engine = engine
        self.exchange_id = exchange_id
        self.api_key = api_key
        self.secret = secret
        self.symbol = symbol
        self.sync_interval = sync_interval
        self.sandbox = sandbox
        self._exchange = None
        self._stop = False

    async def _ensure_exchange(self):
        if self._exchange is not None:
            return
        try:
            import ccxt.async_support as ccxt
        except ImportError:
            raise ImportError("請先 pip install ccxt")
        exchange_class = getattr(ccxt, self.exchange_id)
        config = {"enableRateLimit": True}
        if self.api_key and self.secret:
            config["apiKey"] = self.api_key
            config["secret"] = self.secret
        self._exchange = exchange_class(config)
        if self.sandbox:
            self._exchange.set_sandbox_mode(True)

    async def sync_once(self) -> bool:
        """
        同步一次

        Returns:
            True if synced, False if no change
        """
        await self._ensure_exchange()
        try:
            positions = await self._exchange.fetch_positions([self.symbol])
        except Exception as e:
            logger.exception(f"查詢持倉失敗: {e}")
            return False

        local_pos = self.engine.portfolio.get_position()
        exchange_pos = 0.0

        for p in positions:
            if p["symbol"] == self.symbol:
                # 合約數量，正=多，負=空
                exchange_pos = float(p.get("contracts", 0)) * (
                    1 if p.get("side") == "long" else -1
                )
                break

        # 比對
        if abs(exchange_pos - local_pos) > 1e-6:
            logger.warning(
                f"持倉不同步: 本地={local_pos} 交易所={exchange_pos}，開始修復"
            )
            await self._reconcile(exchange_pos)
            return True
        return False

    async def _reconcile(self, target_position: float) -> None:
        """修復持倉差異（用 FillEvent 補單）"""
        current = self.engine.portfolio.get_position()
        diff = target_position - current

        if abs(diff) < 1e-6:
            return

        # 生成修補 FillEvent
        side = OrderSide.BUY if diff > 0 else OrderSide.SELL
        fill = FillEvent(
            timestamp=datetime.now(tz=timezone.utc),
            side=side,
            quantity=abs(diff),
            price=0,  # 用市價，execution handler 會補
            commission=0,
            slippage=0,
            order_id=f"reconcile_{int(asyncio.get_event_loop().time() * 1000)}",
            is_close=False,  # 這是新倉調整
        )
        # 直接餵給 portfolio
        self.engine.portfolio.handle(fill)
        logger.info(f"持倉已修復: {current} → {target_position}")

    async def run(self) -> None:
        """主迴圈：定期同步"""
        logger.info(f"持倉同步啟動（每 {self.sync_interval} 秒）")
        while not self._stop:
            try:
                await self.sync_once()
            except Exception as e:
                logger.exception(f"同步錯誤: {e}")
            await asyncio.sleep(self.sync_interval)

    def stop(self) -> None:
        self._stop = True
