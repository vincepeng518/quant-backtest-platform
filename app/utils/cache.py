from __future__ import annotations

import json
import logging
from typing import Optional

import redis
from app.config import settings

logger = logging.getLogger(__name__)


class Cache:
    def __init__(self) -> None:
        self._client: Optional[redis.Redis] = None
        self._enabled = True

    def _ensure(self) -> Optional[redis.Redis]:
        if not self._enabled:
            return None
        if self._client is None:
            try:
                self._client = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=1)
                self._client.ping()
            except Exception:
                logger.warning("Redis unavailable — cache disabled")
                self._enabled = False
                return None
        return self._client

    def get(self, key: str) -> Optional[dict]:
        c = self._ensure()
        if c is None:
            return None
        try:
            val = c.get(key)
            return json.loads(val) if val else None
        except Exception:
            return None

    def set(self, key: str, data: dict, ttl: int = 3600) -> None:
        c = self._ensure()
        if c is None:
            return
        try:
            c.setex(key, ttl, json.dumps(data, default=str))
        except Exception:
            pass

    def delete(self, key: str) -> None:
        c = self._ensure()
        if c is None:
            return
        try:
            c.delete(key)
        except Exception:
            pass


cache = Cache()