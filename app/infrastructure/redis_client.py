"""Cliente Redis compartido (publicación sync, suscripción async en SSE)."""

from __future__ import annotations

import logging
from typing import Optional

import redis
import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_sync_redis: Optional[redis.Redis] = None
_async_redis: Optional[aioredis.Redis] = None


def connect_redis() -> None:
    global _sync_redis, _async_redis
    try:
        _sync_redis = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        _sync_redis.ping()
        _async_redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        logger.info("Redis conectado en %s", settings.REDIS_URL)
    except Exception as exc:
        logger.warning("Redis no disponible; eventos en tiempo real deshabilitados: %s", exc)
        _sync_redis = None
        _async_redis = None


async def disconnect_redis_async() -> None:
    global _sync_redis, _async_redis
    if _sync_redis is not None:
        try:
            _sync_redis.close()
        except Exception:
            pass
        _sync_redis = None
    if _async_redis is not None:
        try:
            await _async_redis.aclose()
        except Exception:
            pass
        _async_redis = None


def disconnect_redis() -> None:
    """Cierre sync (fallback); preferir disconnect_redis_async en lifespan."""
    global _sync_redis, _async_redis
    if _sync_redis is not None:
        try:
            _sync_redis.close()
        except Exception:
            pass
        _sync_redis = None
    _async_redis = None


def get_sync_redis() -> Optional[redis.Redis]:
    return _sync_redis


def get_async_redis() -> Optional[aioredis.Redis]:
    return _async_redis
