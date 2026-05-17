"""SSE: cambios de configuración tenant en tiempo real."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.db.models.user import User
from app.dependencies import get_current_user
from app.infrastructure.redis_client import get_async_redis
from app.services.tenant_config_events import CHANNEL_GLOBAL, company_channel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["tenant-events"])

HEARTBEAT_SEC = 25


async def _sse_generator(company_id) -> AsyncIterator[str]:
    yield ": connected\n\n"

    redis = get_async_redis()
    if redis is None:
        while True:
            await asyncio.sleep(HEARTBEAT_SEC)
            yield ": heartbeat\n\n"
        return

    pubsub = redis.pubsub()
    company_ch = company_channel(company_id)
    await pubsub.subscribe(company_ch, CHANNEL_GLOBAL)
    last_heartbeat = time.monotonic()
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message.get("type") == "message":
                data = message.get("data")
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                if data:
                    yield f"data: {data}\n\n"
            now = time.monotonic()
            if now - last_heartbeat >= HEARTBEAT_SEC:
                yield ": heartbeat\n\n"
                last_heartbeat = now
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("SSE stream error company=%s: %s", company_id, exc)
    finally:
        try:
            await pubsub.unsubscribe(company_ch, CHANNEL_GLOBAL)
            await pubsub.aclose()
        except Exception:
            pass


@router.get("/stream")
async def stream_tenant_config_events(
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    return StreamingResponse(
        _sse_generator(current_user.company_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
