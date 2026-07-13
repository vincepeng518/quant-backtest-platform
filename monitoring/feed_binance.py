from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

BINANCE_WS = "wss://stream.binance.com:9443/ws"


class BinanceWsFeed:
    """Phase 1: Binance 秒級 BTC 現貨報價 (websocket trade stream)。
    回調 on_tick(price, ts) 供上游引擎使用。
    """

    def __init__(self, symbol: str = "btcusdt@trade") -> None:
        self.symbol = symbol
        self._ws = None
        self._on_tick: Optional[Callable] = None
        self._running = False

    def on_tick(self, cb: Callable[[float, float], None]) -> None:
        self._on_tick = cb

    async def run(self) -> None:
        import websockets
        self._running = True
        while self._running:
            try:
                async with websockets.connect(f"{BINANCE_WS}/{self.symbol}") as ws:
                    async for msg in ws:
                        if not self._running:
                            break
                        d = json.loads(msg)
                        price = float(d["p"])
                        ts = float(d["T"]) / 1000.0  # ms -> s
                        if self._on_tick:
                            self._on_tick(price, ts)
            except Exception as e:
                logger.warning("Binance WS error: %s; reconnect in 3s", e)
                await asyncio.sleep(3)

    def stop(self) -> None:
        self._running = False
