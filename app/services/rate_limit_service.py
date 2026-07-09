"""Rate limiting usando Redis (con fallback a memoria)."""

from __future__ import annotations

import time
from collections import defaultdict

from app.infrastructure.redis_client import get_sync_redis


class RateLimiter:
    def __init__(self, max_requests: int = 10, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._fallback: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        redis_client = get_sync_redis()
        if redis_client is not None:
            return self._redis_check(redis_client, key)
        return self._memory_check(key)

    def _redis_check(self, client, key: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds
        rkey = f"ratelimit:auth:{key}"
        pipe = client.pipeline()
        pipe.zremrangebyscore(rkey, 0, window_start)
        pipe.zcard(rkey)
        pipe.zadd(rkey, {str(now): now})
        pipe.expire(rkey, self.window_seconds + 1)
        _, count, _, _ = pipe.execute()
        return int(count) < self.max_requests

    def _memory_check(self, key: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds
        requests = self._fallback[key]
        requests = [t for t in requests if t > window_start]
        self._fallback[key] = requests
        if len(requests) >= self.max_requests:
            return False
        requests.append(now)
        return True


def login_rate_limiter() -> RateLimiter:
    return RateLimiter(max_requests=10, window_seconds=60)


def strict_login_rate_limiter() -> RateLimiter:
    return RateLimiter(max_requests=5, window_seconds=60)


def public_tracking_rate_limiter() -> RateLimiter:
    return RateLimiter(max_requests=60, window_seconds=60)
