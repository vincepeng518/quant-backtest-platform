"""app/api/routes/realtime_ws.py — BingX WS 實時 K 線 + 模擬撮合 → FastAPI WebSocket 端點。

前端連 `/api/ws/kline`,訂閱 `{symbol,timeframe}`,每根 kline 推
`{type:'kline', symbol, close, ts, latency_ms, connected, matches_total}`。

斷線/無法重連 → 推 `{type:'error', message}` 並關閉。不碰歷史回測/既有 API。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from engine.realtime import RealtimeKlineFeed

logger = logging.getLogger("realtime_ws")
router = APIRouter(prefix="/api/ws", tags=["realtime-ws"])


@router.websocket("/kline")
async def ws_kline(ws: WebSocket):
    await ws.accept()
    feed: Optional[RealtimeKlineFeed] = None
    feed_task = None
    try:
        # 1) 訂閱訊息
        try:
            sub_raw = await asyncio.wait_for(ws.receive_text(), timeout=15)
            sub = json.loads(sub_raw)
        except Exception:
            await ws.send_json({"type": "error", "message": "訂閱格式需 {symbol,timeframe}"})
            await ws.close(code=1008)
            return
        symbol = str(sub.get("symbol") or "BTC-USDT")
        timeframe = str(sub.get("timeframe") or "1m")
        logger.info("ws kline 訂閱: %s@kline_%s", symbol, timeframe)
        await ws.send_json({"type": "status", "status": "subscribing", "channel": f"{symbol}@kline_{timeframe}"})

        # 2) feed on_kline → 推 kline+延遲到 ws
        async def push(payload: dict) -> None:
            try:
                await ws.send_json({"type": "kline", **payload})
            except Exception:
                pass

        feed = RealtimeKlineFeed(symbol=symbol, timeframe=timeframe, on_kline=push)

        # 3) 後台跑 feed(無限)
        feed_task = asyncio.create_task(feed.run(n_ticks=0))

        # 4) 維持 ws,直到 client 關閉或 feed 無法重連
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=8)
                # client 主動發送 → 當作關閉請求(訂閱一次即可)
                await ws.send_json({"type": "status", "status": "closing", "message": raw})
                break
            except asyncio.TimeoutError:
                # 心跳維持
                if feed.connected is False and feed.disconnect_logs:
                    await ws.send_json({"type": "error", "message": feed.disconnect_logs[-1]})
                    break
                continue
            except Exception:
                break
    except WebSocketDisconnect:
        logger.info("ws kline client 斷線")
    except Exception as e:
        logger.warning("ws kline error: %s", e)
        try:
            await ws.send_json({"type": "error", "message": f"連線失敗/無法重連: {type(e).__name__}: {str(e)[:200]}"})
        except Exception:
            pass
    finally:
        if feed is not None:
            feed.close()
        if feed_task is not None:
            feed_task.cancel()
