"""Esqueleto webhook Stripe (no activo sin STRIPE_WEBHOOK_SECRET)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["platform-webhooks"])


@router.post("/stripe")
async def stripe_webhook(request: Request) -> dict[str, str]:
    secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", None)
    if not secret:
        raise HTTPException(status_code=501, detail="Stripe webhook no configurado")
    body = await request.body()
    logger.info("Stripe webhook recibido (%d bytes); implementar verify + apply_subscription_event", len(body))
    return {"status": "not_implemented"}
