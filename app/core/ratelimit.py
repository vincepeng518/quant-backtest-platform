"""app/core/ratelimit.py — 極簡滑動視窗速率限制。

用途：公開站台（PUBLIC_MODE=demo）允許匿名跑回測，但那是真 CPU。
沒有配額就等於把算力免費送人，所以匿名運算端點按 IP 限流。

單機 in-memory 即可（本後端是單一 uvicorn process）。重啟清空是可接受的
取捨；真要防繞過再上 Redis。
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    """每個 key（通常是 IP）在 window 秒內最多 limit 次。"""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = float(window_seconds)
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            cutoff = now - self.window
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True

    def retry_after(self, key: str) -> float:
        """回傳最快可再嘗試的秒數（供 Retry-After 標頭）。"""
        with self._lock:
            q = self._hits.get(key)
            if not q:
                return 0.0
            return max(0.0, self.window - (time.monotonic() - q[0]))

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def anon_limit() -> SlidingWindowLimiter:
    """匿名配額（預設 20 次/小時）。"""
    return SlidingWindowLimiter(
        limit=int(os.getenv("ANON_RATE_LIMIT", "20")),
        window_seconds=float(os.getenv("ANON_RATE_WINDOW_SECONDS", "3600")),
    )


# 模組級單例：middleware 共用
anon_limiter = anon_limit()
