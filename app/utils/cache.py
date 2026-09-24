from __future__ import annotations

import json
import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Optional

import redis
from app.config import settings

logger = logging.getLogger(__name__)

# In-process fallback bound (single uvicorn worker on the VPS; MemoryMax 2.5G).
_MEM_MAX_ENTRIES = 32


class Cache:
    """Redis cache with an in-process TTL/LRU fallback when Redis is unavailable."""

    def __init__(self) -> None:
        self._client: Optional[redis.Redis] = None
        self._enabled = True
        self._mem: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()

    def _ensure(self) -> Optional[redis.Redis]:
        if not self._enabled:
            return None
        if self._client is None:
            try:
                self._client = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=1)
                self._client.ping()
            except Exception:
                logger.warning("Redis unavailable — using in-process cache")
                self._client = None
                self._enabled = False
                return None
        return self._client

    def _mem_get(self, key: str) -> Optional[Any]:
        with self._lock:
            item = self._mem.get(key)
            if item is None:
                return None
            expires, val = item
            if expires < time.monotonic():
                self._mem.pop(key, None)
                return None
            self._mem.move_to_end(key)
            return val

    def _mem_set(self, key: str, data: Any, ttl: int) -> None:
        with self._lock:
            self._mem[key] = (time.monotonic() + ttl, data)
            self._mem.move_to_end(key)
            while len(self._mem) > _MEM_MAX_ENTRIES:
                self._mem.popitem(last=False)

    def get(self, key: str) -> Optional[Any]:
        c = self._ensure()
        if c is None:
            return self._mem_get(key)
        try:
            val = c.get(key)
            return json.loads(val) if val else None
        except Exception:
            return None

    def set(self, key: str, data: Any, ttl: int = 3600) -> None:
        c = self._ensure()
        if c is None:
            self._mem_set(key, data, ttl)
            return
        try:
            c.setex(key, ttl, json.dumps(data, default=str))
        except Exception:
            pass

    def delete(self, key: str) -> None:
        c = self._ensure()
        if c is None:
            with self._lock:
                self._mem.pop(key, None)
            return
        try:
            c.delete(key)
        except Exception:
            pass


cache = Cache()
