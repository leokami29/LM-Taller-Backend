"""Revisión de configuración tenant y publicación Redis para SSE."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID

from app.db.models.company import Company
from app.infrastructure.redis_client import get_sync_redis
from app.services import platform_config_service as pcfg

logger = logging.getLogger(__name__)

CONFIG_REVISION_KEY = "config_revision"
GLOBAL_REVISION_KEY = "global_config_revision"
EVENT_TYPE = "tenant.config_changed"
CHANNEL_COMPANY_PREFIX = "tenant:events:"
CHANNEL_GLOBAL = "tenant:events:global"


class TenantConfigReason(str, Enum):
    SESSION_POLICY = "session_policy"
    GLOBAL_SESSION = "global_session"
    SUBSCRIPTION = "subscription"
    COMPANY_STATUS = "company_status"
    ENTITLEMENTS = "entitlements"


def company_channel(company_id: UUID) -> str:
    return f"{CHANNEL_COMPANY_PREFIX}{company_id}"


def read_company_config_revision(company: Company) -> int:
    raw = company.settings_json or {}
    try:
        return int(raw.get(CONFIG_REVISION_KEY, 0))
    except (TypeError, ValueError):
        return 0


def bump_company_config_revision(company: Company) -> int:
    settings = dict(company.settings_json or {})
    revision = int(settings.get(CONFIG_REVISION_KEY, 0)) + 1
    settings[CONFIG_REVISION_KEY] = revision
    company.settings_json = settings
    return revision


def read_global_config_revision() -> int:
    config = pcfg.load_config()
    meta = config.get("meta") or {}
    try:
        return int(meta.get(GLOBAL_REVISION_KEY, 0))
    except (TypeError, ValueError):
        return 0


def bump_global_config_revision() -> int:
    config = pcfg.load_config()
    meta = dict(config.get("meta") or {})
    revision = int(meta.get(GLOBAL_REVISION_KEY, 0)) + 1
    meta[GLOBAL_REVISION_KEY] = revision
    config["meta"] = meta
    pcfg.save_config(config)
    return revision


def _event_payload(
    *,
    scope: str,
    company_id: UUID | None,
    reason: TenantConfigReason,
    revision: int,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": EVENT_TYPE,
        "scope": scope,
        "company_id": str(company_id) if company_id else None,
        "reason": reason.value,
        "revision": revision,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    if meta:
        payload["meta"] = meta
    return payload


def _publish(channel: str, payload: dict[str, Any]) -> None:
    client = get_sync_redis()
    if client is None:
        return
    try:
        client.publish(channel, json.dumps(payload, ensure_ascii=False))
    except Exception as exc:
        logger.warning("No se pudo publicar en Redis (%s): %s", channel, exc)


def publish_company_event(
    company_id: UUID,
    reason: TenantConfigReason,
    revision: int,
    *,
    meta: dict[str, Any] | None = None,
) -> None:
    payload = _event_payload(
        scope="company",
        company_id=company_id,
        reason=reason,
        revision=revision,
        meta=meta,
    )
    _publish(company_channel(company_id), payload)


def publish_global_event(
    reason: TenantConfigReason,
    revision: int,
    *,
    meta: dict[str, Any] | None = None,
) -> None:
    payload = _event_payload(
        scope="global",
        company_id=None,
        reason=reason,
        revision=revision,
        meta=meta,
    )
    _publish(CHANNEL_GLOBAL, payload)


def notify_company_config_changed(
    company_id: UUID,
    reason: TenantConfigReason,
    revision: int,
    *,
    meta: dict[str, Any] | None = None,
) -> None:
    publish_company_event(company_id, reason, revision, meta=meta)


def notify_company_after_commit(
    company: Company,
    reason: TenantConfigReason,
    *,
    meta: dict[str, Any] | None = None,
) -> int:
    """Tras commit en DB: publica con la revisión ya persistida en company."""
    revision = read_company_config_revision(company)
    notify_company_config_changed(company.id, reason, revision, meta=meta)
    return revision


def bump_and_notify_company(
    company: Company,
    reason: TenantConfigReason,
    *,
    meta: dict[str, Any] | None = None,
) -> int:
    """Incrementa revisión en el objeto company (persistir con commit)."""
    revision = bump_company_config_revision(company)
    notify_company_config_changed(company.id, reason, revision, meta=meta)
    return revision


def bump_and_notify_global(
    reason: TenantConfigReason,
    *,
    meta: dict[str, Any] | None = None,
) -> int:
    revision = bump_global_config_revision()
    publish_global_event(reason, revision, meta=meta)
    return revision


def post_company_mutation(
    company_id: UUID,
    reason: TenantConfigReason,
    *,
    meta: dict[str, Any] | None = None,
) -> int | None:
    """Incrementa revisión en la DB del tenant y publica (tras mutación ya persistida)."""
    from app.config import settings
    from app.db.session import SessionLocal, tenant_session_for_company

    def _bump(db) -> int | None:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            return None
        revision = bump_company_config_revision(company)
        db.add(company)
        db.commit()
        notify_company_config_changed(company_id, reason, revision, meta=meta)
        return revision

    if settings.USE_TENANT_DATABASE_ROUTING:
        with tenant_session_for_company(company_id) as db:
            return _bump(db)
    db = SessionLocal()
    try:
        return _bump(db)
    finally:
        db.close()


def company_patch_meta(
    company: Company,
    *,
    current_period_end: datetime | None = None,
) -> dict[str, Any]:
    status = company.subscription_status
    status_val = status.value if hasattr(status, "value") else str(status)
    meta: dict[str, Any] = {
        "is_active": company.is_active,
        "subscription_status": status_val,
    }
    if company.billing_email:
        meta["billing_email"] = company.billing_email
    if current_period_end is not None:
        if isinstance(current_period_end, datetime):
            meta["current_period_end"] = current_period_end.isoformat()
        else:
            meta["current_period_end"] = str(current_period_end)
    return meta
