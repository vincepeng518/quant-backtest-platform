"""
Live Trading: 即時 K 線資料源

把 CCXT websocket 的 K 線轉成 BarEvent，餵給 EventEngine。

支援：
- Binance / BingX / OKX / Bybit 等 CCXT 交易所
- 訂閱多個交易對
- 自動重連
- WebSocket 訊息佇列
"""
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional, Callable
from datetime import datetime, timezone

import pandas as pd

from events import BarEvent

logger = logging.getLogger(__name__)


class CCXTBarsFeed:
    """
    從 CCXT websocket 取得 K 線 → BarEvent

    用法：
        feed = CCXTBarsFeed(symbol="BTC/USDT", timeframe="1m")
        feed.on_bar(lambda bar: engine.dispatch(bar))
        await feed.start()
    """

    def __init__(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "1m",
        exchange_id: str = "binance",
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.exchange_id = exchange_id
        self._callbacks: List[Callable[[BarEvent], None]] = []
        self._stop = False
        self._buffer: List[BarEvent] = []
        self._last_bar: Optional[BarEvent] = None

    def on_bar(self, callback: Callable[[BarEvent], None]) -> None:
        """註冊 K 線 callback"""
        self._callbacks.append(callback)

    def _emit(self, bar: BarEvent) -> None:
        """廣播 K 線給所有 callback"""
        # 去重：同 timestamp 不重複發
        if self._last_bar is not None and self._last_bar.timestamp == bar.timestamp:
            return
        self._last_bar = bar
        for cb in self._callbacks:
            try:
                cb(bar)
            except Exception as e:
                logger.exception(f"Callback 失敗: {e}")

    async def start(self) -> None:
        """
        啟動 websocket 連線，持續接收 K 線

        需先 pip install ccxt
        """
        try:
            import ccxt.async_support as ccxt
        except ImportError:
            raise ImportError("請先 pip install ccxt")

        exchange_class = getattr(ccxt, self.exchange_id)
        exchange = exchange_class({"enableRateLimit": True})
        await exchange.load_markets()

        logger.info(f"開始訂閱 {self.symbol} {self.timeframe} K 線 ({self.exchange_id})")

        while not self._stop:
            try:
                # 訂閱 K 線
                async for ohlcv in exchange.watch_ohlcv(self.symbol, self.timeframe):
                    if self._stop:
                        break
                    # ohlcv 格式: [timestamp, open, high, low, close, volume]
                    timestamp, o, h, l, c, v = ohlcv
                    bar = BarEvent(
                        timestamp=pd.Timestamp(timestamp, unit="ms", tz="UTC").tz_convert(None),
                        open=o, high=h, low=l, close=c, volume=v,
                        symbol=self.symbol,
                    )
                    self._emit(bar)
            except Exception as e:
                logger.exception(f"WebSocket 錯誤: {e}")
                if not self._stop:
                    logger.info("5 秒後重連...")
                    await asyncio.sleep(5)

        await exchange.close()
        logger.info("已停止 websocket")

    def stop(self) -> None:
        """停止 websocket"""
        self._stop = True


class ReplayFeed:
    """
    重播模式：從歷史 CSV / DataFrame 餵 K 線

    用於：
    - 測試
    - 模擬 live trading
    - paper trading
    """

    def __init__(self, df: pd.DataFrame, speed: float = 1.0):
        """
        Args:
            df: OHLCV 資料
            speed: 播放速度（1.0=即時，10=10倍速）
        """
        if "timestamp" in df.columns:
            df = df.set_index("timestamp")
        self.df = df.sort_index()
        self.speed = speed
        self._callbacks: List[Callable[[BarEvent], None]] = []
        self._stop = False

    def on_bar(self, callback: Callable[[BarEvent], None]) -> None:
        self._callbacks.append(callback)

    async def start(self) -> None:
        """逐根 K 線送出（模擬 live）"""
        import time
        for timestamp, row in self.df.iterrows():
            if self._stop:
                break
            bar = BarEvent.from_row(timestamp, row)
            for cb in self._callbacks:
                try:
                    cb(bar)
                except Exception as e:
                    logger.exception(f"Callback 失敗: {e}")
            # 模擬即時（按 timeframe 間隔）
            if self.speed > 0:
                # 計算與上一根的時間差
                idx = self.df.index.get_loc(timestamp)
                if idx > 0:
                    prev_ts = self.df.index[idx - 1]
                    delta = (timestamp - prev_ts).total_seconds()
                    await asyncio.sleep(delta / self.speed)
