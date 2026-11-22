from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

import redis

from app.core.config import get_settings


class RateLimitExceeded(Exception):
    """Raised when a caller exceeds the configured request budget."""


class RateLimiter:
    """Redis-backed fixed-window rate limiter with thread-safe in-memory fallback."""

    def __init__(self) -> None:
        self._local_counts: dict[str, tuple[int, float]] = defaultdict(lambda: (0, 0.0))
        self._lock = Lock()
        self._redis_client: redis.Redis | None = None

    def _get_redis(self) -> redis.Redis | None:
        settings = get_settings()
        if settings.ENVIRONMENT == "test":
            return None
        if self._redis_client is None:
            try:
                self._redis_client = redis.Redis.from_url(
                    settings.REDIS_URL,
                    socket_connect_timeout=1,
                    socket_timeout=1,
                )
            except Exception:
                return None
        return self._redis_client

    def check(self, key: str, max_requests: int, window_seconds: int) -> None:
        client = self._get_redis()
        if client is not None:
            try:
                pipe = client.pipeline()
                pipe.incr(key)
                pipe.expire(key, window_seconds, nx=True)
                count, _ = pipe.execute()
                if int(count) > max_requests:
                    raise RateLimitExceeded("Rate limit exceeded")
                return
            except RateLimitExceeded:
                raise
            except Exception:
                # Fall back gracefully if Redis is transiently unreachable
                pass

        now = time.monotonic()
        with self._lock:
            count, window_start = self._local_counts[key]
            if now - window_start >= window_seconds:
                self._local_counts[key] = (1, now)
                return
            if count + 1 > max_requests:
                raise RateLimitExceeded("Rate limit exceeded")
            self._local_counts[key] = (count + 1, window_start)


rate_limiter = RateLimiter()
