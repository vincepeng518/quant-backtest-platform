"""
Live Trading: 通知服務

當發生重要事件（成交/風控/錯誤）時發送通知。
支援 Telegram、Discord、Email。
"""
from __future__ import annotations

import logging
from typing import Optional
from datetime import datetime

from events import FillEvent, OrderEvent

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Telegram 通知"""

    def __init__(self, bot_token: str = "", chat_id: str = ""):
        self.bot_token = bot_token
        self.chat_id = chat_id

    async def send(self, message: str) -> None:
        if not (self.bot_token and self.chat_id):
            logger.debug(f"[Telegram dry-run] {message}")
            return
        try:
            import aiohttp
        except ImportError:
            logger.warning("請先 pip install aiohttp")
            return

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        async with aiohttp.ClientSession() as session:
            await session.post(url, json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
            })


class DiscordNotifier:
    """Discord Webhook 通知"""

    def __init__(self, webhook_url: str = ""):
        self.webhook_url = webhook_url

    async def send(self, message: str) -> None:
        if not self.webhook_url:
            logger.debug(f"[Discord dry-run] {message}")
            return
        try:
            import aiohttp
        except ImportError:
            logger.warning("請先 pip install aiohttp")
            return

        async with aiohttp.ClientSession() as session:
            await session.post(self.webhook_url, json={
                "content": message,
            })


class NotificationHub:
    """
    通知中心

    統一管理多個通知管道。
    """

    def __init__(self):
        self.telegram: Optional[TelegramNotifier] = None
        self.discord: Optional[DiscordNotifier] = None

    def setup_telegram(self, bot_token: str, chat_id: str) -> None:
        self.telegram = TelegramNotifier(bot_token, chat_id)

    def setup_discord(self, webhook_url: str) -> None:
        self.discord = DiscordNotifier(webhook_url)

    async def notify_fill(self, fill: FillEvent) -> None:
        """成交通知"""
        side = "🟢 買" if fill.side.value == "BUY" else " 賣"
        msg = (
            f"{side} {fill.symbol} {fill.quantity} @ {fill.price:.2f}\n"
            f"手續費: {fill.commission:.4f}\n"
            f"時間: {fill.timestamp}"
        )
        await self._send(msg)

    async def notify_order(self, order: OrderEvent) -> None:
        """下單通知"""
        side = "買" if order.side.value == "BUY" else "賣"
        order_type = order.order_type.value
        msg = f" {side}單 {order_type} {order.quantity} @ {order.price}"
        await self._send(msg)

    async def notify_risk(self, message: str) -> None:
        """風控通知"""
        msg = f" 風控：{message}"
        await self._send(msg)

    async def notify_error(self, error: Exception) -> None:
        """錯誤通知"""
        msg = f" 錯誤：{type(error).__name__}: {error}"
        await self._send(msg)

    async def _send(self, message: str) -> None:
        if self.telegram:
            await self.telegram.send(message)
        if self.discord:
            await self.discord.send(message)
