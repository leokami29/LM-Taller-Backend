"""Sincronización de suscripciones catálogo → tenant companies."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.enums import PlanTier, SubscriptionStatus
from app.core.features import PLAN_DEFAULTS
from app.db.models.company import Company
from app.services.plan_catalog_service import (
    get_plan_definition,
    resolve_limits,
    resolve_modules,
)


def apply_plan_to_company(
    db: Session,
    company_id: UUID,
    *,
    plan_code: str,
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
    billing_email: str | None = None,
    catalog_db: Session | None = None,
    entitlements_override: dict | None = None,
) -> Company | None:
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return None
    tier = PlanTier(plan_code)
    if catalog_db is not None:
        defn = get_plan_definition(catalog_db, plan_code)
        limits = resolve_limits(defn, entitlements_override)
        modules = resolve_modules(defn, entitlements_override)
        max_users = limits.get("max_users")
        max_orders = limits.get("max_orders_month")
        storage = limits.get("storage_mb")
    else:
        defaults = PLAN_DEFAULTS.get(tier.value, PLAN_DEFAULTS["starter"])
        modules = list(defaults["modules"])
        max_users = defaults.get("max_users")
        max_orders = defaults.get("max_orders_month")
        storage = defaults.get("storage_mb")
        if entitlements_override:
            if entitlements_override.get("modules"):
                modules = list(entitlements_override["modules"])
            if entitlements_override.get("max_users") is not None:
                max_users = entitlements_override["max_users"]
            if entitlements_override.get("max_orders_month") is not None:
                max_orders = entitlements_override["max_orders_month"]
            if entitlements_override.get("storage_mb") is not None:
                storage = entitlements_override["storage_mb"]
    company.plan = tier
    company.subscription_status = status
    company.active_users_limit = max_users
    if billing_email:
        company.billing_email = billing_email
    settings = dict(company.settings_json or {})
    ent = settings.get("entitlements") or {}
    ent["modules"] = modules
    ent["max_orders_month"] = max_orders
    ent["storage_mb"] = storage
    settings["entitlements"] = ent
    company.settings_json = settings
    db.add(company)
    db.commit()
    db.refresh(company)
    return company
