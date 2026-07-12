"""
Live Trading: 主引擎

整合所有 live 元件：
- 即時 K 線（CCXTBarsFeed）
- 訂單路由（CCXTOrderRouter）
- 持倉同步（PositionSync）
- 通知（NotificationHub）
- 同一個 EventEngine 核心

啟動：
    engine = LiveTradingEngine(
        symbol="BTC/USDT",
        exchange_id="binance",
        api_key=os.environ["BINANCE_API_KEY"],
        secret=os.environ["BINANCE_SECRET"],
    )
    await engine.start()
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional, Callable
from datetime import datetime

from engine import EventEngine
from events import BarEvent, FillEvent, OrderEvent
from live.data_feed import CCXTBarsFeed, ReplayFeed
from live.order_router import CCXTOrderRouter
from live.position_sync import PositionSync
from live.notification import NotificationHub

logger = logging.getLogger(__name__)


class LiveTradingEngine:
    """
    即時交易引擎

    與回測共用同一個 EventEngine 核心，
    只差在：
    - BarEvent 來源：backtest 是 from df，live 是 websocket
    - OrderEvent 出口：backtest 是模擬交易所，live 是真實下單
    - FillEvent 來源：backtest 是模擬，live 是訂單成交回報
    """

    def __init__(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "1m",
        exchange_id: str = "binance",
        api_key: str = "",
        secret: str = "",
        strategy_code: str = "",
        strategy_params: Optional[dict] = None,
        sandbox: bool = True,
        initial_capital: float = 10000.0,
        dry_run: bool = False,  # True=不下單，只回報
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.exchange_id = exchange_id
        self.strategy_code = strategy_code
        self.strategy_params = strategy_params or {}
        self.dry_run = dry_run

        # === 核心 EventEngine ===
        self.engine = EventEngine(
            initial_capital=initial_capital,
            commission=0.001,
            slippage=0.0005,
        )
        # 設定策略
        if strategy_code:
            # 預熱用一個空的 df（之後會更新）
            import pandas as pd
            empty_df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
            self.engine.set_strategy(strategy_code, self.strategy_params, empty_df)

        # === Live 元件 ===
        self.feed = CCXTBarsFeed(
            symbol=symbol, timeframe=timeframe, exchange_id=exchange_id
        )
        self.router = CCXTOrderRouter(
            exchange_id=exchange_id,
            api_key=api_key if not dry_run else "",
            secret=secret if not dry_run else "",
            sandbox=sandbox,
        )
        self.sync = PositionSync(
            engine=self.engine,
            exchange_id=exchange_id,
            api_key=api_key if not dry_run else "",
            secret=secret if not dry_run else "",
            symbol=symbol,
            sandbox=sandbox,
        )
        self.notifier = NotificationHub()

        # 連接：Bar → Engine，Engine Order → Router，Router Fill → Engine
        self.feed.on_bar(self._on_bar)
        self.router.set_fill_callback(self._on_fill)

        self._stop = False

    def setup_notifications(self, telegram_bot_token: str = "", telegram_chat_id: str = "",
                            discord_webhook: str = "") -> None:
        """設定通知管道"""
        if telegram_bot_token and telegram_chat_id:
            self.notifier.setup_telegram(telegram_bot_token, telegram_chat_id)
        if discord_webhook:
            self.notifier.setup_discord(discord_webhook)

    def _on_bar(self, bar: BarEvent) -> None:
        """收到 K 線 → 餵給 Engine"""
        # 同步 current_bar 給 execution handler（市價單需要）
        self.engine.execution.set_current_bar(bar)
        # 分發
        self.engine._queue.append(bar)
        # 把 queue 中所有事件處理完
        while self.engine._queue:
            ev = self.engine._queue.popleft()
            self.engine._dispatch(ev)
        # 同步 RiskManager
        self.engine.risk.update_position(self.engine.portfolio.position)

    def _on_fill(self, fill: FillEvent) -> None:
        """收到成交 → 餵給 Engine portfolio"""
        self.engine.portfolio.handle(fill)
        # 同步 RiskManager
        self.engine.risk.update_position(self.engine.portfolio.position)
        # 通知
        asyncio.create_task(self._notify_fill(fill))

    async def _notify_fill(self, fill: FillEvent) -> None:
        fill.symbol = self.symbol
        await self.notifier.notify_fill(fill)

    async def start(self) -> None:
        """
        啟動 live trading
        """
        logger.info(f"啟動 Live Trading: {self.symbol} {self.timeframe} ({self.exchange_id})")
        if self.dry_run:
            logger.info("[DRY-RUN 模式] 不會實際下單")

        # 啟動 3 個並行任務
        await asyncio.gather(
            self.feed.start(),
            self.sync.run(),
            self._monitor_orders(),
        )

    async def _monitor_orders(self) -> None:
        """定期查詢訂單狀態"""
        while not self._stop:
            try:
                await self.router.poll_pending_orders()
            except Exception as e:
                logger.exception(f"查詢訂單失敗: {e}")
            await asyncio.sleep(5)

    def stop(self) -> None:
        self._stop = True
        self.feed.stop()
        self.sync.stop()


async def run_paper_trading(strategy_code: str, params: dict,
                            df, symbol: str = "TEST/USDT") -> dict:
    """
    便利函式：用歷史資料跑 paper trading

    完整模擬從 K 線到成交的流程，但不下單。
    """
    # 用 ReplayFeed 模擬 live K 線流
    feed = ReplayFeed(df, speed=0)  # 0=不 sleep，立即跑

    # EventEngine + dry-run 路由
    engine = EventEngine(initial_capital=10000, commission=0.001, slippage=0.0005)
    router = CCXTOrderRouter(dry_run=True)  # paper trading

    # 設定策略（先用預算模式簡化）
    # 這裡省略策略細節，使用者可用自己的方式

    # 連接
    def on_bar(bar: BarEvent):
        engine.execution.set_current_bar(bar)
        engine._queue.append(bar)
        while engine._queue:
            ev = engine._queue.popleft()
            engine._dispatch(ev)

    feed.on_bar(on_bar)
    await feed.start()

    return {
        "trades": engine.portfolio.trades,
        "equity_curve": engine.portfolio.equity_curve,
    }
