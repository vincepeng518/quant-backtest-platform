from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

BINANCE_WS = "wss://stream.binance.com:9443/ws"


class BinanceWsFeed:
    """Phase 1: Binance 秒級 BTC 現貨報價 (websocket trade stream)。

    回調 on_tick(price, ts) 供上游引擎使用。帶指數退避重連。
    """

    def __init__(self, symbol: str = "btcusdt@trade") -> None:
        self.symbol = symbol
        self._on_tick: Optional[Callable] = None
        self._running = False

    def on_tick(self, cb: Callable[[float, float], None]) -> None:
        self._on_tick = cb

    async def run(self) -> None:
        import websockets
        self._running = True
        attempt = 0
        while self._running:
            try:
                async with websockets.connect(
                    f"{BINANCE_WS}/{self.symbol}",
                ) as ws:
                    logger.info("[FEED] connected %s", self.symbol)
                    attempt = 0
                    async for msg in ws:
                        if not self._running:
                            break
                        try:
                            d = json.loads(msg)
                        except json.JSONDecodeError:
                            continue
                        # 只處理 trade 事件 (含 p/T 欄位)
                        if "p" not in d or "T" not in d:
                            continue
                        try:
                            price = float(d["p"])
                            ts = float(d["T"]) / 1000.0
                        except (KeyError, ValueError, TypeError):
                            continue
                        if self._on_tick:
                            self._on_tick(price, ts)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                attempt += 1
                backoff = min(30, 3 * attempt)
                logger.warning("[FEED] error (attempt %d): %s; reconnect in %ds",
                               attempt, e, backoff)
                await asyncio.sleep(backoff)

    def stop(self) -> None:
        self._running = False
