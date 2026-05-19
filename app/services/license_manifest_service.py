"""Construcción y firma de manifiestos de licencia desktop."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.dt import utc_now
from app.core.entitlements import Entitlements
from app.core.enums import PlanTier
from app.core.features import ALL_MODULES
from app.core.plan_desktop_policy import desktop_policy_for_plan
from app.core.subscription_lifecycle import subscription_block_reason, subscription_is_usable
from app.db.models.company import Company
from app.schemas.license import LicenseManifestPayload, SignedLicenseManifest
from app.services.license_signing import sign_manifest_payload
from app.services.permission_service import PermissionService
from app.services.tenant_config_events import read_company_config_revision, read_global_config_revision


def _license_valid_until(
    *,
    status: str,
    period_end: datetime | None,
    grace_days: int,
    now: datetime,
) -> datetime:
    if status in ("suspended", "cancelled"):
        return now
    candidates: list[datetime] = [now + timedelta(days=grace_days)]
    if period_end is not None:
        end = period_end
        if end.tzinfo is None and now.tzinfo is not None:
            end = end.replace(tzinfo=now.tzinfo)
        candidates.append(end + timedelta(days=grace_days))
        candidates.append(end)
    return max(candidates)


def build_license_manifest(
    db: Session,
    *,
    company: Company,
    tenant_slug: str,
    seat_id: UUID,
    installation_id: str,
) -> SignedLicenseManifest:
    svc = PermissionService(db)
    ent: Entitlements = svc.get_entitlements(company.id)
    period_end = svc.get_subscription_period_end(company.id)
    policy = desktop_policy_for_plan(ent.plan)
    now = utc_now()
    usable = subscription_is_usable(ent.status, period_end, now=now)
    block = subscription_block_reason(ent.status, period_end, now=now)
    valid_until = _license_valid_until(
        status=ent.status.value if hasattr(ent.status, "value") else str(ent.status),
        period_end=period_end,
        grace_days=policy.offline_grace_days,
        now=now,
    )
    modules = sorted(m for m in ent.modules if m in ALL_MODULES)

    payload = LicenseManifestPayload(
        company_id=company.id,
        tenant_slug=tenant_slug,
        plan=ent.plan.value if isinstance(ent.plan, PlanTier) else str(ent.plan),
        subscription_status=ent.status.value if hasattr(ent.status, "value") else str(ent.status),
        subscription_usable=usable,
        subscription_block_reason=block,
        current_period_end=period_end,
        offline_grace_days=policy.offline_grace_days,
        max_days_without_sync=policy.max_days_without_sync,
        license_valid_until=valid_until,
        seat_id=seat_id,
        installation_id=installation_id,
        active_seats_limit=policy.active_seats_limit,
        server_time=now,
        config_revision=read_company_config_revision(company),
        global_config_revision=read_global_config_revision(),
        modules=modules,
        limits={
            "max_users": ent.max_users,
            "max_orders_month": ent.max_orders_month,
            "storage_mb": ent.storage_mb,
        },
        issued_at=now,
        key_id="v1",
    )
    manifest_dict = payload.model_dump(mode="json")
    signature = sign_manifest_payload(manifest_dict, key_id=payload.key_id)
    return SignedLicenseManifest(manifest=payload, signature=signature)
