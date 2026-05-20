"""Planes del catálogo: módulos, límites, precios y política desktop."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.features import ALL_MODULES, PLAN_DEFAULTS
from app.core.plan_desktop_policy import DesktopPlanPolicy
from app.db.catalog.models import Plan, PlanEntitlement
from app.services import platform_config_service as pcfg

PLAN_CODES = ("starter", "pro", "enterprise")

_LIMIT_KEYS = ("max_users", "max_orders_month", "storage_mb")
_DESKTOP_KEYS = ("offline_grace_days", "max_days_without_sync", "active_seats_limit")
_PRICING_KEYS = ("monthly_price_cop", "default_period_days")


def _defaults_for(code: str) -> dict[str, Any]:
    base = PLAN_DEFAULTS.get(code, PLAN_DEFAULTS["starter"])
    json_cfg = pcfg.load_config().get("plans", {}).get(code, {})
    modules = sorted(base.get("modules") or [])
    return {
        "code": code,
        "name": code.capitalize(),
        "modules": modules,
        "max_users": int(json_cfg.get("max_active_users") or base.get("max_users") or 5),
        "max_orders_month": base.get("max_orders_month"),
        "storage_mb": base.get("storage_mb"),
        "monthly_price_cop": int(json_cfg.get("monthly_price_cop") or 99000),
        "default_period_days": 30,
        "offline_grace_days": {"starter": 7, "pro": 14, "enterprise": 30}.get(code, 7),
        "max_days_without_sync": {"starter": 14, "pro": 30, "enterprise": 90}.get(code, 14),
        "active_seats_limit": {"starter": 1, "pro": 3, "enterprise": 10}.get(code, 1),
    }


def _entitlements_map(catalog_db: Session, plan_id: UUID) -> dict[str, Any]:
    rows = catalog_db.query(PlanEntitlement).filter(PlanEntitlement.plan_id == plan_id).all()
    out: dict[str, Any] = {}
    for row in rows:
        out[row.feature_code] = row.value_json
    return out


def get_plan_definition(catalog_db: Session, code: str) -> dict[str, Any]:
    """Definición efectiva del plan (catálogo + defaults + platform_config)."""
    merged = _defaults_for(code)
    plan = catalog_db.query(Plan).filter(Plan.code == code).first()
    if plan:
        merged["name"] = plan.name
        ent = _entitlements_map(catalog_db, plan.id)
        if "modules" in ent:
            raw_mod = ent["modules"]
            if isinstance(raw_mod, dict) and "modules" in raw_mod:
                merged["modules"] = list(raw_mod["modules"])
            elif isinstance(raw_mod, list):
                merged["modules"] = raw_mod
        for key in _LIMIT_KEYS + _DESKTOP_KEYS + _PRICING_KEYS:
            if key not in ent or ent[key] is None:
                continue
            raw = ent[key]
            if isinstance(raw, dict) and key in raw:
                merged[key] = raw[key]
            elif not isinstance(raw, dict):
                merged[key] = raw
    return merged


def list_plan_definitions(catalog_db: Session) -> list[dict[str, Any]]:
    return [get_plan_definition(catalog_db, code) for code in PLAN_CODES]


def desktop_policy_from_definition(defn: dict[str, Any]) -> DesktopPlanPolicy:
    return DesktopPlanPolicy(
        offline_grace_days=int(defn.get("offline_grace_days") or 7),
        max_days_without_sync=int(defn.get("max_days_without_sync") or 14),
        active_seats_limit=int(defn.get("active_seats_limit") or 1),
    )


def desktop_policy_for_plan_code(catalog_db: Session, plan_code: str) -> DesktopPlanPolicy:
    return desktop_policy_from_definition(get_plan_definition(catalog_db, plan_code))


def resolve_modules(defn: dict[str, Any], override: dict[str, Any] | None = None) -> list[str]:
    modules = set(defn.get("modules") or [])
    if override and override.get("modules"):
        modules = set(override["modules"])
    return sorted(m for m in modules if m in ALL_MODULES)


def resolve_limits(defn: dict[str, Any], override: dict[str, Any] | None = None) -> dict[str, int | None]:
    out = {
        "max_users": defn.get("max_users"),
        "max_orders_month": defn.get("max_orders_month"),
        "storage_mb": defn.get("storage_mb"),
    }
    if override:
        for key in _LIMIT_KEYS:
            if key in override and override[key] is not None:
                out[key] = override[key]
    return out


def save_plan_definition(catalog_db: Session, code: str, payload: dict[str, Any]) -> dict[str, Any]:
    plan = catalog_db.query(Plan).filter(Plan.code == code).first()
    if not plan:
        raise ValueError(f"Plan {code} no existe en catálogo")
    catalog_db.query(PlanEntitlement).filter(PlanEntitlement.plan_id == plan.id).delete()
    modules = payload.get("modules") or []
    catalog_db.add(
        PlanEntitlement(plan_id=plan.id, feature_code="modules", value_json={"modules": modules})
    )
    for key in _LIMIT_KEYS + _DESKTOP_KEYS + _PRICING_KEYS:
        if key in payload:
            catalog_db.add(
                PlanEntitlement(plan_id=plan.id, feature_code=key, value_json={key: payload[key]})
            )
    cfg = pcfg.load_config()
    cfg.setdefault("plans", {})[code] = {
        "monthly_price_cop": int(payload.get("monthly_price_cop") or 0),
        "max_active_users": int(payload.get("max_users") or 5),
    }
    pcfg.save_config(cfg)
    catalog_db.flush()
    return get_plan_definition(catalog_db, code)


def list_features(catalog_db: Session) -> list[dict[str, str]]:
    from app.db.catalog.models import FeatureCatalog

    rows = catalog_db.query(FeatureCatalog).order_by(FeatureCatalog.code).all()
    return [{"code": r.code, "name": r.name, "kind": r.kind} for r in rows]
