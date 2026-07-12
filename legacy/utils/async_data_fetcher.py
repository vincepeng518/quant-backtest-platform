"""
異步資料抓取模組

將 CCXT 資料抓取和回測引擎移出 Streamlit 主執行緒，
防止 API 超時導致整個介面卡死。

架構：
- ThreadPoolExecutor 處理同步的 CCXT 抓取
- 結果透過 session_state 傳遞給前端
- 未來可替換為 asyncio + aiohttp 異步實作
"""
from __future__ import annotations

import concurrent.futures
from typing import Optional
import pandas as pd

_executor: Optional[concurrent.futures.ThreadPoolExecutor] = None


def get_executor() -> concurrent.futures.ThreadPoolExecutor:
    """取得或建立共用的 ThreadPoolExecutor"""
    global _executor
    if _executor is None:
        _executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
    return _executor


def fetch_data_async(fetch_fn, *args, **kwargs) -> concurrent.futures.Future:
    """在背景執行緒中執行資料抓取"""
    executor = get_executor()
    return executor.submit(fetch_fn, *args, **kwargs)


def get_future_result(future: concurrent.futures.Future, timeout: float = 0.1) -> tuple:
    """非阻塞地檢查 Future 狀態"""
    if not future.done():
        return ("pending", None)
    try:
        return ("done", future.result(timeout=timeout))
    except Exception as e:
        return ("error", str(e))


def run_backtest_async(backtest_fn, *args, **kwargs) -> concurrent.futures.Future:
    """在背景執行緒中執行回測"""
    executor = get_executor()
    return executor.submit(backtest_fn, *args, **kwargs)


__all__ = [
    "get_executor",
    "fetch_data_async",
    "get_future_result",
    "run_backtest_async",
]
