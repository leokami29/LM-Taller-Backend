"""Asignación manual de planes (catálogo opcional + sync tenant)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.core.permissions import PLATFORM_BILLING_READ, PLATFORM_COMPANIES_WRITE
from app.db.models.company import Company
from app.db.models.platform_user import PlatformUser
from app.db.session import catalog_session_scope, get_db, tenant_session_for_company
from app.dependencies import RequirePlatformPermission
from app.schemas.subscription import SubscriptionAssign, SubscriptionResponse
from app.services.subscription_service import apply_plan_to_company

router = APIRouter(prefix="/companies", tags=["platform-subscriptions"])


def _sync_tenant_plan(company_id: UUID, payload: SubscriptionAssign, db: Session) -> Company | None:
    if settings.USE_TENANT_DATABASE_ROUTING:
        with tenant_session_for_company(company_id) as tenant_db:
            return apply_plan_to_company(
                tenant_db,
                company_id,
                plan_code=payload.plan_code,
                status=payload.status,
                billing_email=str(payload.billing_email) if payload.billing_email else None,
            )
    return apply_plan_to_company(
        db,
        company_id,
        plan_code=payload.plan_code,
        status=payload.status,
        billing_email=str(payload.billing_email) if payload.billing_email else None,
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
        else:
            catalog_db.add(
                Subscription(
                    company_id=company_id,
                    plan_id=plan.id,
                    status=payload.status,
                    billing_email=str(payload.billing_email) if payload.billing_email else None,
                    current_period_end=payload.current_period_end,
                    provider="manual",
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


def _catalog_period_end(company_id: UUID):
    if not settings.USE_TENANT_DATABASE_ROUTING:
        return None
    from app.db.catalog.models import Subscription

    with catalog_session_scope() as catalog_db:
        sub = catalog_db.query(Subscription).filter(Subscription.company_id == company_id).first()
        return sub.current_period_end if sub else None


@router.get("/{company_id}/subscription", response_model=SubscriptionResponse)
def get_subscription(
    company_id: UUID,
    _: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_BILLING_READ)),
    db: Session = Depends(get_db),
) -> SubscriptionResponse:
    period_end = _catalog_period_end(company_id)
    if settings.USE_TENANT_DATABASE_ROUTING:
        with tenant_session_for_company(company_id) as tenant_db:
            company = tenant_db.query(Company).filter(Company.id == company_id).first()
    else:
        company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return SubscriptionResponse(
        company_id=company_id,
        plan_code=company.plan.value,
        status=company.subscription_status,
        billing_email=company.billing_email,
        provider="manual",
        current_period_end=period_end,
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

    return SubscriptionResponse(
        company_id=company_id,
        plan_code=payload.plan_code,
        status=payload.status,
        billing_email=str(payload.billing_email) if payload.billing_email else None,
        provider="manual",
        current_period_end=payload.current_period_end,
    )
