"""Asignación manual de planes (catálogo opcional + sync tenant)."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.core.permissions import (
    PLATFORM_BILLING_READ,
    PLATFORM_COMPANIES_READ,
    PLATFORM_COMPANIES_WRITE,
)
from app.db.models.company import Company
from app.db.models.platform_user import PlatformUser
from app.db.session import catalog_session_scope, get_db, tenant_session_for_company
from app.dependencies import RequirePlatformPermission
from app.schemas.subscription import (
    EffectiveEntitlementsSnapshot,
    SubscriptionAssign,
    SubscriptionResponse,
)
from app.services.effective_entitlements_service import effective_entitlements_snapshot
from app.core.dt import utc_now
from app.schemas.license import SignedLicenseManifest
from app.services.license_manifest_service import build_license_manifest
from app.services import plan_catalog_service as pcs
from app.services.subscription_service import apply_plan_to_company
from app.services.tenant_config_events import TenantConfigReason, company_patch_meta, post_company_mutation
from app.db.catalog.models import Subscription, TenantRouting

router = APIRouter(prefix="/companies", tags=["platform-subscriptions"])


def _sync_tenant_plan(company_id: UUID, payload: SubscriptionAssign, db: Session) -> Company | None:
    override = payload.entitlements_override_json or None
    if settings.USE_TENANT_DATABASE_ROUTING:
        with catalog_session_scope() as catalog_db:
            with tenant_session_for_company(company_id) as tenant_db:
                return apply_plan_to_company(
                    tenant_db,
                    company_id,
                    plan_code=payload.plan_code,
                    status=payload.status,
                    billing_email=str(payload.billing_email) if payload.billing_email else None,
                    catalog_db=catalog_db,
                    entitlements_override=override,
                )
    return apply_plan_to_company(
        db,
        company_id,
        plan_code=payload.plan_code,
        status=payload.status,
        billing_email=str(payload.billing_email) if payload.billing_email else None,
        entitlements_override=override,
    )


def _persist_catalog_subscription(
    company_id: UUID,
    payload: SubscriptionAssign,
    actor_id: UUID,
) -> None:
    if not settings.USE_TENANT_DATABASE_ROUTING:
        return
    from app.db.catalog.models import CatalogAuditLog, Plan, Subscription

    with catalog_session_scope() as catalog_db:
        plan = catalog_db.query(Plan).filter(Plan.code == payload.plan_code).first()
        if not plan:
            return
        sub = catalog_db.query(Subscription).filter(Subscription.company_id == company_id).first()
        if sub:
            sub.plan_id = plan.id
            sub.status = payload.status
            if payload.billing_email:
                sub.billing_email = str(payload.billing_email)
            sub.current_period_end = payload.current_period_end
            sub.entitlements_override_json = payload.entitlements_override_json or {}
        else:
            catalog_db.add(
                Subscription(
                    company_id=company_id,
                    plan_id=plan.id,
                    status=payload.status,
                    billing_email=str(payload.billing_email) if payload.billing_email else None,
                    current_period_end=payload.current_period_end,
                    provider="manual",
                    entitlements_override_json=payload.entitlements_override_json or {},
                )
            )
        catalog_db.add(
            CatalogAuditLog(
                actor_type="platform",
                actor_id=str(actor_id),
                company_id=company_id,
                action="subscription_assigned",
                resource_type="subscription",
                resource_id=str(company_id),
                metadata_json={"plan_code": payload.plan_code, "status": payload.status.value},
            )
        )
        catalog_db.commit()


def _catalog_subscription_row(company_id: UUID) -> Subscription | None:
    if not settings.USE_TENANT_DATABASE_ROUTING:
        return None
    with catalog_session_scope() as catalog_db:
        return catalog_db.query(Subscription).filter(Subscription.company_id == company_id).first()


def _build_subscription_response(
    company: Company,
    *,
    company_id: UUID,
    period_end,
    override_json: dict | None = None,
    catalog_db: Session | None = None,
) -> SubscriptionResponse:
    override = dict(override_json or {})
    if settings.USE_TENANT_DATABASE_ROUTING:
        if catalog_db is not None:
            sub = catalog_db.query(Subscription).filter(Subscription.company_id == company_id).first()
            if sub and not override_json:
                override = dict(sub.entitlements_override_json or {})
            snap = effective_entitlements_snapshot(company, catalog_db=catalog_db)
        else:
            with catalog_session_scope() as cdb:
                sub = cdb.query(Subscription).filter(Subscription.company_id == company_id).first()
                if sub and not override_json:
                    override = dict(sub.entitlements_override_json or {})
                snap = effective_entitlements_snapshot(company, catalog_db=cdb)
    else:
        snap = effective_entitlements_snapshot(company)

    return SubscriptionResponse(
        company_id=company_id,
        plan_code=company.plan.value,
        status=company.subscription_status,
        billing_email=company.billing_email,
        provider="manual",
        current_period_end=period_end,
        entitlements_override_json=override,
        effective_entitlements=EffectiveEntitlementsSnapshot(**snap),
    )


@router.get("/{company_id}/subscription", response_model=SubscriptionResponse)
def get_subscription(
    company_id: UUID,
    _: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_BILLING_READ)),
    db: Session = Depends(get_db),
) -> SubscriptionResponse:
    sub_row = _catalog_subscription_row(company_id)
    period_end = sub_row.current_period_end if sub_row else None
    override = dict(sub_row.entitlements_override_json or {}) if sub_row else {}
    if settings.USE_TENANT_DATABASE_ROUTING:
        with catalog_session_scope() as catalog_db:
            with tenant_session_for_company(company_id) as tenant_db:
                company = tenant_db.query(Company).filter(Company.id == company_id).first()
                if not company:
                    raise HTTPException(status_code=404, detail="Empresa no encontrada")
                return _build_subscription_response(
                    company,
                    company_id=company_id,
                    period_end=period_end,
                    override_json=override,
                    catalog_db=catalog_db,
                )
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return _build_subscription_response(
        company,
        company_id=company_id,
        period_end=period_end,
        override_json=override,
    )


@router.post("/{company_id}/subscription", response_model=SubscriptionResponse)
def assign_subscription(
    company_id: UUID,
    payload: SubscriptionAssign,
    actor: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_WRITE)),
    db: Session = Depends(get_db),
) -> SubscriptionResponse:
    company = _sync_tenant_plan(company_id, payload, db)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    _persist_catalog_subscription(company_id, payload, actor.id)
    if company:
        period_end = payload.current_period_end or _catalog_period_end(company_id)
        post_company_mutation(
            company_id,
            TenantConfigReason.SUBSCRIPTION,
            meta=company_patch_meta(company, current_period_end=period_end),
        )

    period_end = payload.current_period_end or _catalog_period_end(company_id)
    if settings.USE_TENANT_DATABASE_ROUTING:
        with catalog_session_scope() as catalog_db:
            with tenant_session_for_company(company_id) as tenant_db:
                company = tenant_db.query(Company).filter(Company.id == company_id).first()
                if not company:
                    raise HTTPException(status_code=404, detail="Empresa no encontrada")
                return _build_subscription_response(
                    company,
                    company_id=company_id,
                    period_end=period_end,
                    override_json=payload.entitlements_override_json or {},
                    catalog_db=catalog_db,
                )
    return _build_subscription_response(
        company,
        company_id=company_id,
        period_end=period_end,
        override_json=payload.entitlements_override_json or {},
    )


def _catalog_period_end(company_id: UUID):
    sub = _catalog_subscription_row(company_id)
    return sub.current_period_end if sub else None


class SubscriptionRenewRequest(BaseModel):
    days: int | None = Field(default=None, ge=1, le=730)
    mode: str | None = Field(default=None, pattern="^(extend_30|renew_monthly)$")


@router.post("/{company_id}/subscription/renew", response_model=SubscriptionResponse)
def renew_subscription(
    company_id: UUID,
    body: SubscriptionRenewRequest,
    actor: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_WRITE)),
    db: Session = Depends(get_db),
) -> SubscriptionResponse:
    if not settings.USE_TENANT_DATABASE_ROUTING:
        raise HTTPException(status_code=501, detail="Renovación requiere catálogo multi-tenant")
    from app.db.catalog.models import CatalogAuditLog, Plan, Subscription

    now = utc_now()
    with catalog_session_scope() as catalog_db:
        sub = catalog_db.query(Subscription).filter(Subscription.company_id == company_id).first()
        if not sub:
            raise HTTPException(status_code=404, detail="Suscripción no encontrada")
        plan = catalog_db.query(Plan).filter(Plan.id == sub.plan_id).first()
        defn = pcs.get_plan_definition(catalog_db, plan.code if plan else "starter")
        if body.mode == "extend_30":
            delta_days = 30
        elif body.mode == "renew_monthly":
            delta_days = int(defn.get("default_period_days") or 30)
        else:
            delta_days = body.days or 30
        base = sub.current_period_end if sub.current_period_end and sub.current_period_end > now else now
        sub.current_period_end = base + timedelta(days=delta_days)
        catalog_db.add(
            CatalogAuditLog(
                actor_type="platform",
                actor_id=str(actor.id),
                company_id=company_id,
                action="subscription_renewed",
                resource_type="subscription",
                resource_id=str(company_id),
                metadata_json={"days": delta_days, "mode": body.mode},
            )
        )
        catalog_db.commit()
        period_end = sub.current_period_end
        plan_code = plan.code if plan else "starter"
        status = sub.status
        billing_email = sub.billing_email

    if settings.USE_TENANT_DATABASE_ROUTING:
        with tenant_session_for_company(company_id) as tenant_db:
            company = tenant_db.query(Company).filter(Company.id == company_id).first()
            if company:
                post_company_mutation(
                    company_id,
                    TenantConfigReason.SUBSCRIPTION,
                    meta=company_patch_meta(company, current_period_end=period_end),
                )

    if settings.USE_TENANT_DATABASE_ROUTING:
        with catalog_session_scope() as catalog_db:
            with tenant_session_for_company(company_id) as tenant_db:
                company = tenant_db.query(Company).filter(Company.id == company_id).first()
                if not company:
                    raise HTTPException(status_code=404, detail="Empresa no encontrada")
                return _build_subscription_response(
                    company,
                    company_id=company_id,
                    period_end=period_end,
                    catalog_db=catalog_db,
                )

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return _build_subscription_response(
        company,
        company_id=company_id,
        period_end=period_end,
    )


@router.get("/{company_id}/license-preview", response_model=SignedLicenseManifest)
def license_preview(
    company_id: UUID,
    installation_id: str = Query(..., min_length=8),
    db: Session = Depends(get_db),
    _user: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_READ)),
) -> SignedLicenseManifest:
    if not settings.USE_TENANT_DATABASE_ROUTING:
        raise HTTPException(status_code=501, detail="Vista previa requiere routing multi-tenant")
    from uuid import uuid4

    with catalog_session_scope() as catalog_db:
        routing = catalog_db.query(TenantRouting).filter(TenantRouting.company_id == company_id).first()
        if not routing:
            raise HTTPException(status_code=404, detail="Empresa no encontrada")
        slug = routing.slug
    with tenant_session_for_company(company_id) as tenant_db:
        company = tenant_db.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail="Empresa no encontrada")
        return build_license_manifest(
            tenant_db,
            company=company,
            tenant_slug=slug,
            seat_id=uuid4(),
            installation_id=installation_id,
        )
