"""Sincronización de suscripciones catálogo → tenant companies."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.enums import PlanTier, SubscriptionStatus
from app.core.features import PLAN_DEFAULTS
from app.db.models.company import Company


def apply_plan_to_company(
    db: Session,
    company_id: UUID,
    *,
    plan_code: str,
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
    billing_email: str | None = None,
) -> Company | None:
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return None
    tier = PlanTier(plan_code)
    defaults = PLAN_DEFAULTS.get(tier.value, PLAN_DEFAULTS["starter"])
    company.plan = tier
    company.subscription_status = status
    company.active_users_limit = defaults.get("max_users")
    if billing_email:
        company.billing_email = billing_email
    settings = dict(company.settings_json or {})
    ent = settings.get("entitlements") or {}
    ent["modules"] = list(defaults["modules"])
    ent["max_orders_month"] = defaults.get("max_orders_month")
    ent["storage_mb"] = defaults.get("storage_mb")
    settings["entitlements"] = ent
    company.settings_json = settings
    db.add(company)
    db.commit()
    db.refresh(company)
    return company
