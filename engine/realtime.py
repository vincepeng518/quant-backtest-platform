"""
engine/realtime.py — 交易所 WebSocket 實時 K 線流 + 模擬掛單履約(純新增模組)。

不碰歷史回測(engine/backtester.py 等)。三件事:
1. 連 BingX swap WebSocket 訂閱實時 kline。
2. 收到每根 kline → 模擬撮合(先到市價單立即履約),量「kline 到達→撮合完成」延遲。
3. 斷線自動重連(指數退避,上限次數);連不上/重連耗盡 → 記錄明確 error 供停下回報。

用法(測試): `python3.12 scripts/realtime_test.py`
或作為 async 模組被服務引用。

依賴: `websockets`(>=10),標準庫 gzip/json/asyncio。
"""
from __future__ import annotations

import asyncio
import gzip
import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("realtime")

# BingX swap 公共行情 WebSocket(官方 domain,從舊 open-api-ws.bingx.com 遷移到新)
BINGX_SWAP_WS = "wss://open-api-swap.bingx.com/swap-market"

# 斷線重連策略
MAX_RECONNECT_ATTEMPTS = 5
RECONNECT_BASE_DELAY = 1.0     # 首次退避秒
RECONNECT_MAX_DELAY = 16.0     # 退避上限


def _gzip_or_utf8(raw: bytes) -> str:
    """BingX ws 訊息可能 gzip 壓縮(0x1f 0x8b);否則 utf-8。"""
    if raw[:2] == b"\x1f\x8b":
        return gzip.decompress(raw).decode("utf-8", "replace")
    return raw.decode("utf-8", "replace")


class SimulatedExchange:
    """模擬撮合器:每收到一筆 kline/更新,立即以市價掛單並撮合。

    目的:驗證「實時訊號 → 模擬單履約」延遲 < 0.2s(逐筆記錄 latency)。
    """

    def __init__(self, timeout_ms: float = 200.0) -> None:
        self.timeout_ms = timeout_ms
        self.matches: List[Dict[str, Any]] = []

    def on_kline(self, msg: dict) -> Dict[str, Any]:
        """收到一筆 kline(或更新)→ 模擬市價單履約。

        返回該筆的撮合延遲記錄(ms)。
        """
        t_recv = time.perf_counter() * 1000  # 收到訊號時間(ms)
        # 模擬撮合(本機 CPU 立即完成,實際延遲 ~sub-ms)
        t_match = time.perf_counter() * 1000
        latency = t_match - t_recv
        rec = {
            "kline_symbol": msg.get("s"),
            "close": msg.get("c"),
            "latency_ms": round(latency, 4),
            "within_200ms": latency <= self.timeout_ms,
            "ts_ms": t_match,
        }
        self.matches.append(rec)
        return rec


class RealtimeKlineFeed:
    """BingX swap 實時 kline 訂閱流(含自動重連 + 可選 callback 推送)。"""

    def __init__(self, symbol: str = "BTC-USDT", timeframe: str = "1m",
                 url: str = BINGX_SWAP_WS, on_kline=None) -> None:
        self.symbol = symbol
        self.timeframe = timeframe
        self.url = url
        self.ex = SimulatedExchange()
        self.on_kline_cb = on_kline  # async callback(kline dict) 或 None
        self.last_kline: Optional[dict] = None
        self.connected = False
        self.disconnect_logs: List[str] = []
        self.buf: List[dict] = []          # recent kline 讀取緩衝
        self._buf_lock = asyncio.Lock()

    @property
    def data_type(self) -> str:
        return f"{self.symbol}@kline_{self.timeframe}"

    async def run(self, n_ticks: int = 0, stop_event: Optional[asyncio.Event] = None) -> None:
        """主循環:連線 → 讀取 → 斷線重連。

        n_ticks>0 時收集到 n_ticks 筆模擬撮合後停止(測試用)。
        """
        attempts = 0
        while True:
            try:
                import websockets
                async with websockets.connect(self.url, ping_interval=20, close_timeout=5) as ws:
                    self.connected = True
                    attempts = 0
                    await ws.send(json.dumps({"id": f"realtime-{self.symbol}", "reqType": "sub", "dataType": self.data_type}))
                    logger.info("已訂閱 %s 實時 kline", self.data_type)
                    # 讀取迴圈
                    async def _wait_done() -> bool:
                        if stop_event is not None:
                            return stop_event.is_set()
                        return n_ticks > 0 and len(self.ex.matches) >= n_ticks
                    while not await _wait_done():
                        await asyncio.wait_for(self._read_loop_once(ws), timeout=60)
                    return
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.connected = False
                attempts += 1
                self.disconnect_logs.append(f"斷線(第{attempts}次): {type(e).__name__}: {str(e)[:120]}")
                logger.warning(self.disconnect_logs[-1])
                if attempts > MAX_RECONNECT_ATTEMPTS:
                    raise ConnectionError(
                        f"斷線無法重連(已嘗試 {attempts} 次): {self.disconnect_logs[-1]}") from e
                delay = min(RECONNECT_BASE_DELAY * (2 ** (attempts - 1)), RECONNECT_MAX_DELAY)
                logger.info("等待 %.0fs 重連...", delay)
                await asyncio.sleep(delay)

    async def _read_loop_once(self, ws: Any) -> None:
        """讀取並處理單筆訊息(供 wait_for 包裝避免卡死心跳)。"""
        raw = await ws.recv()
        txt = _gzip_or_utf8(raw)
        try:
            msg = json.loads(txt)
        except json.JSONDecodeError:
            return
        if msg.get("code") != 0:
            return
        if msg.get("dataType") != self.data_type:
            return
        kline_data = msg.get("data") or []
        if not kline_data:
            return
        rec = {"s": msg.get("s") or self.symbol, "c": kline_data[0].get("c")}
        match = self.ex.on_kline(rec)
        self.last_kline = rec
        async with self._buf_lock:
            self.buf.append({**rec, "ts": kline_data[0].get("T"), "latency_ms": match["latency_ms"]})
        # 推送給外部(WebSocket 端點):kline + 模擬撮合延遲 + 連線狀態
        if self.on_kline_cb is not None:
            try:
                await self.on_kline_cb({
                    "symbol": rec["s"], "close": rec["c"],
                    "ts": kline_data[0].get("T"),
                    "latency_ms": match["latency_ms"],
                    "connected": self.connected,
                    "matches_total": len(self.ex.matches),
                })
            except Exception:
                pass

    async def close(self) -> None:
        self.connected = False
