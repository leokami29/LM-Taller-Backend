"""Catálogo unificado de planes y features."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.permissions import PLATFORM_COMPANIES_READ, PLATFORM_COMPANIES_WRITE
from app.db.models.platform_user import PlatformUser
from app.db.session import catalog_session_scope
from app.dependencies import RequirePlatformPermission
from app.services import plan_catalog_service as pcs
from app.services.tenant_config_events import TenantConfigReason, bump_and_notify_global

router = APIRouter(prefix="/catalog", tags=["platform-catalog"])


class PlanDefinitionUpdate(BaseModel):
    modules: list[str] = Field(default_factory=list)
    max_users: int | None = None
    max_orders_month: int | None = None
    storage_mb: int | None = None
    monthly_price_cop: int | None = None
    offline_grace_days: int | None = None
    max_days_without_sync: int | None = None
    active_seats_limit: int | None = None
    default_period_days: int | None = None


@router.get("/features")
def list_features(
    _user: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_READ)),
) -> list[dict[str, str]]:
    with catalog_session_scope() as catalog_db:
        return pcs.list_features(catalog_db)


@router.get("/plans")
def list_plans(
    _user: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_READ)),
) -> list[dict[str, Any]]:
    with catalog_session_scope() as catalog_db:
        return pcs.list_plan_definitions(catalog_db)


@router.put("/plans/{plan_code}")
def update_plan(
    plan_code: str,
    payload: PlanDefinitionUpdate,
    _user: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_WRITE)),
) -> dict[str, Any]:
    if plan_code not in pcs.PLAN_CODES:
        raise HTTPException(status_code=404, detail="Plan no encontrado")
    with catalog_session_scope() as catalog_db:
        try:
            result = pcs.save_plan_definition(catalog_db, plan_code, payload.model_dump(exclude_none=True))
            catalog_db.commit()
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    bump_and_notify_global(TenantConfigReason.ENTITLEMENTS)
    return result
