"""Chat endpoint — proxies LLM with SSE streaming for the platform's AI assistant."""
from __future__ import annotations

import json
import os
from typing import Any

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/chat", tags=["chat"])

_LLM_BASE = os.getenv("LLM_BASE_URL", "https://yuanyuaicloud.cn/v1")
_LLM_KEY = os.getenv("LLM_API_KEY", os.getenv("GLM_API_KEY", ""))
_LLM_MODEL = os.getenv("LLM_MODEL", "glm-5.2")

SYSTEM_PROMPT = """你是 Quant Platform 的 AI 交易助手，服務於一位專業量化交易者。

## 你的能力邊界
- 你可以討論策略設計、回測方法論、風險管理、統計驗證
- 你可以分析用戶貼上的回測結果、績效指標、權益曲線
- 你可以協助 Pine Script / Python 策略代碼撰寫與除錯
- 你可以解釋 Sharpe、Sortino、Profit Factor、Max Drawdown 等指標
- 你可以討論 Walk-Forward、Monte Carlo、參數優化等驗證方法

## 你的風格
- 直接犀利、冷酷客觀、結果導向
- 不溫柔安撫、不長篇說教、不模糊建議、不假樂觀
- 結論先行，細節在後
- 數據說話，不修飾錯誤
- 簡體中文回覆（除非用戶用繁體或英文）

## 你的紅線
- 嚴禁「這次不一樣」式的情緒化判斷
- 嚴禁推薦沒有回測支撐的策略
- 嚴禁忽略樣本數不足的問題
- 嚴禁給出不含風險評估的收益預期

## 核心原則
紀律就是利潤，情緒就是成本。
數據天賦 × 策略思維 × 高速執行 = 在市場中持續賺錢。"""


@router.post("/stream")
async def chat_stream(payload: dict[str, Any]):
    """Stream LLM response as SSE events."""
    messages = payload.get("messages", [])
    if not messages:
        return {"error": "no messages"}

    # Prepend system prompt
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    async def event_stream():
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
                async with client.stream(
                    "POST",
                    f"{_LLM_BASE}/chat/completions",
                    json={
                        "model": _LLM_MODEL,
                        "messages": full_messages,
                        "stream": True,
                        "temperature": 0.4,
                        "max_tokens": 4096,
                    },
                    headers={"Authorization": f"Bearer {_LLM_KEY}"},
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        yield f"data: {json.dumps({'error': f'LLM HTTP {resp.status_code}: {body.decode()[:200]}'})}\n\n"
                        return
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        chunk = line[6:]
                        if chunk.strip() == "[DONE]":
                            yield "data: [DONE]\n\n"
                            return
                        try:
                            obj = json.loads(chunk)
                            choices = obj.get("choices", [])
                            if not choices:
                                continue
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield f"data: {json.dumps({'content': content})}\n\n"
                        except json.JSONDecodeError:
                            continue
        except httpx.ConnectError as e:
            yield f"data: {json.dumps({'error': f'connect: {e}'})}\n\n"
        except httpx.ReadTimeout:
            yield f"data: {json.dumps({'error': 'timeout'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/health")
async def chat_health():
    return {"status": "ok", "model": _LLM_MODEL}
