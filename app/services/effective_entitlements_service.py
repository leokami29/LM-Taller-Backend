"""Entitlements efectivos: catálogo de planes + suscripción + overrides del tenant."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.core.entitlements import Entitlements
from app.core.enums import PlanTier, SubscriptionStatus
from app.core.features import MODULE_CORE
from app.db.catalog.models import Plan, Subscription
from app.db.models.company import Company
from app.db.session import catalog_session_scope
from app.services import plan_catalog_service as pcs


def _scalar_ent_value(raw: Any, key: str) -> Any:
    if raw is None:
        return None
    if isinstance(raw, dict):
        if key in raw:
            return raw[key]
        if key == "modules" and "modules" in raw:
            return raw["modules"]
    return raw


def _plan_entitlements_flat(catalog_db: Session, plan_code: str) -> dict[str, Any]:
    """Plano de feature_code -> valor escalar o lista modules."""
    plan = catalog_db.query(Plan).filter(Plan.code == plan_code).first()
    if not plan:
        return pcs._defaults_for(plan_code)
    defn = pcs.get_plan_definition(catalog_db, plan_code)
    ent_map = pcs._entitlements_map(catalog_db, plan.id)
    flat = dict(defn)
    for feat, raw in ent_map.items():
        val = _scalar_ent_value(raw, feat)
        if val is not None:
            flat[feat] = val
    return flat


def _merge_override_dict(*parts: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for part in parts:
        if not part:
            continue
        for k, v in part.items():
            if v is not None:
                out[k] = v
    return out


def resolve_effective_entitlements(
    company: Company,
    *,
    catalog_db: Session | None = None,
) -> Entitlements:
    """
    plan(catálogo) ⊕ subscriptions.entitlements_override_json ⊕ company.settings_json.entitlements
    """
    plan_code = company.plan.value if hasattr(company.plan, "value") else str(company.plan)
    tier = PlanTier(plan_code) if plan_code else PlanTier.STARTER
    status = (
        SubscriptionStatus(company.subscription_status)
        if company.subscription_status
        else SubscriptionStatus.ACTIVE
    )
    company_ent = (company.settings_json or {}).get("entitlements") or {}

    if not settings.USE_TENANT_DATABASE_ROUTING:
        return Entitlements.from_company_row(
            plan=tier,
            subscription_status=status,
            active_users_limit=company.active_users_limit,
            settings_json=company.settings_json,
        )

    def _resolve(cdb: Session) -> Entitlements:
        flat = _plan_entitlements_flat(cdb, tier.value)
        sub = cdb.query(Subscription).filter(Subscription.company_id == company.id).first()
        catalog_override = dict(sub.entitlements_override_json or {}) if sub else {}
        if sub and sub.status:
            status = (
                SubscriptionStatus(sub.status)
                if not isinstance(sub.status, SubscriptionStatus)
                else sub.status
            )
        merged = _merge_override_dict(catalog_override, company_ent)

        modules = pcs.resolve_modules(flat, merged if merged.get("modules") else catalog_override)
        if merged.get("modules"):
            modules = pcs.resolve_modules({"modules": modules}, merged)

        limits = pcs.resolve_limits(flat, catalog_override)
        for key in ("max_users", "max_orders_month", "storage_mb"):
            if merged.get(key) is not None:
                limits[key] = merged[key]

        max_users = limits.get("max_users")
        if max_users is None:
            max_users = company.active_users_limit

        return Entitlements(
            plan=tier,
            status=status,
            modules=frozenset(str(m) for m in modules if m) or frozenset({MODULE_CORE}),
            max_users=max_users,
            max_orders_month=limits.get("max_orders_month"),
            storage_mb=limits.get("storage_mb"),
        )

    if catalog_db is not None:
        return _resolve(catalog_db)
    with catalog_session_scope() as cdb:
        return _resolve(cdb)


def resolve_effective_entitlements_for_company_id(
    tenant_db: Session,
    company_id: UUID,
    *,
    catalog_db: Session | None = None,
) -> Entitlements:
    company = tenant_db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return Entitlements.default_starter()
    return resolve_effective_entitlements(company, catalog_db=catalog_db)


def effective_entitlements_snapshot(
    company: Company,
    *,
    catalog_db: Session | None = None,
) -> dict[str, Any]:
    """Vista serializable para consola de plataforma."""
    ent = resolve_effective_entitlements(company, catalog_db=catalog_db)
    plan_code = company.plan.value if hasattr(company.plan, "value") else str(company.plan)

    def _with_db(cdb: Session) -> dict[str, Any]:
        defn = pcs.get_plan_definition(cdb, plan_code)
        policy = pcs.desktop_policy_from_definition(defn)
        sub = cdb.query(Subscription).filter(Subscription.company_id == company.id).first()
        catalog_override = dict(sub.entitlements_override_json or {}) if sub else {}
        seats = catalog_override.get("active_seats_limit")
        if seats is None:
            seats = policy.active_seats_limit
        return {
            "modules": sorted(ent.modules),
            "max_users": ent.max_users,
            "max_orders_month": ent.max_orders_month,
            "storage_mb": ent.storage_mb,
            "active_seats_limit": int(seats) if seats is not None else policy.active_seats_limit,
            "monthly_price_cop": int(defn.get("monthly_price_cop") or 0),
        }

    if not settings.USE_TENANT_DATABASE_ROUTING:
        return {
            "modules": sorted(ent.modules),
            "max_users": ent.max_users,
            "max_orders_month": ent.max_orders_month,
            "storage_mb": ent.storage_mb,
            "active_seats_limit": None,
            "monthly_price_cop": None,
        }
    if catalog_db is not None:
        return _with_db(catalog_db)
    with catalog_session_scope() as cdb:
        return _with_db(cdb)
