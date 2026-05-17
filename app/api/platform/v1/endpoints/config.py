from typing import Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.permissions import PLATFORM_COMPANIES_READ, PLATFORM_COMPANIES_WRITE
from app.dependencies import RequirePlatformPermission, require_platform_super_admin
from app.db.models.platform_user import PlatformUser
from app.services import platform_config_service as pcfg
from app.services.tenant_config_events import TenantConfigReason, bump_and_notify_global

router = APIRouter(prefix="/config", tags=["platform-config"])


class PlanConfig(BaseModel):
    monthly_price_cop: int
    max_active_users: int


class GlobalConfig(BaseModel):
    plans: Dict[str, PlanConfig]


class SessionConfig(BaseModel):
    """TTL de JWT; aplica en el próximo login o refresh exitoso."""

    tenant_access_token_minutes: int = Field(
        ge=pcfg.ACCESS_MIN_MINUTES,
        le=pcfg.ACCESS_MAX_MINUTES,
    )
    tenant_refresh_token_days: int = Field(
        ge=pcfg.REFRESH_MIN_DAYS,
        le=pcfg.REFRESH_MAX_DAYS,
    )
    platform_access_token_minutes: int = Field(
        ge=pcfg.ACCESS_MIN_MINUTES,
        le=pcfg.ACCESS_MAX_MINUTES,
    )
    platform_refresh_token_days: int = Field(
        ge=pcfg.REFRESH_MIN_DAYS,
        le=pcfg.REFRESH_MAX_DAYS,
    )


class SessionConfigResponse(SessionConfig):
    effective_from: str = "next_login_or_refresh"


@router.get("/plans", response_model=GlobalConfig)
def get_plans_config(
    _user: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_READ)),
):
    config = pcfg.load_config()
    return {"plans": config["plans"]}


@router.put("/plans", response_model=GlobalConfig)
def update_plans_config(
    payload: GlobalConfig,
    _user: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_WRITE)),
):
    config = pcfg.load_config()
    config["plans"] = payload.model_dump()["plans"]
    pcfg.save_config(config)
    bump_and_notify_global(TenantConfigReason.ENTITLEMENTS)
    return {"plans": config["plans"]}


@router.get("/session", response_model=SessionConfigResponse)
def get_session_config(
    _user: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_READ)),
):
    s = pcfg.get_session_settings()
    return SessionConfigResponse(
        tenant_access_token_minutes=s.tenant_access_token_minutes,
        tenant_refresh_token_days=s.tenant_refresh_token_days,
        platform_access_token_minutes=s.platform_access_token_minutes,
        platform_refresh_token_days=s.platform_refresh_token_days,
    )


@router.put("/session", response_model=SessionConfigResponse)
def update_session_config(
    payload: SessionConfig,
    _user: PlatformUser = Depends(require_platform_super_admin),
):
    s = pcfg.update_session_settings(payload.model_dump())
    bump_and_notify_global(TenantConfigReason.GLOBAL_SESSION)
    return SessionConfigResponse(
        tenant_access_token_minutes=s.tenant_access_token_minutes,
        tenant_refresh_token_days=s.tenant_refresh_token_days,
        platform_access_token_minutes=s.platform_access_token_minutes,
        platform_refresh_token_days=s.platform_refresh_token_days,
    )
