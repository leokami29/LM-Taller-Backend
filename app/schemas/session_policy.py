from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.services import platform_config_service as pcfg

PolicyModeSchema = Literal["inherit", "explicit"]
PolicySourceSchema = Literal["global", "company", "site", "user"]


class SessionPolicyEntrySchema(BaseModel):
    mode: PolicyModeSchema = "inherit"
    access_token_minutes: Optional[int] = Field(
        default=None,
        ge=pcfg.ACCESS_MIN_MINUTES,
        le=pcfg.ACCESS_MAX_MINUTES,
    )
    refresh_token_days: Optional[int] = Field(
        default=None,
        ge=pcfg.REFRESH_MIN_DAYS,
        le=pcfg.REFRESH_MAX_DAYS,
    )


class SessionEffectiveSchema(BaseModel):
    access_token_minutes: int
    refresh_token_days: int
    source: PolicySourceSchema


class GlobalSessionDefaultsSchema(BaseModel):
    access_token_minutes: int
    refresh_token_days: int


class SessionPolicyScopeEffective(BaseModel):
    id: Optional[UUID] = None
    entry: SessionPolicyEntrySchema
    effective: SessionEffectiveSchema


class SessionPolicyDocumentResponse(BaseModel):
    global_defaults: GlobalSessionDefaultsSchema
    company: SessionPolicyEntrySchema
    company_effective: SessionEffectiveSchema
    sites: list[SessionPolicyScopeEffective]
    users: list[SessionPolicyScopeEffective]


class CompanySessionPolicyUpdate(BaseModel):
    entry: SessionPolicyEntrySchema
    apply_to_all_sites: bool = False


class SiteSessionPolicyUpdate(BaseModel):
    entry: SessionPolicyEntrySchema


class UserSessionPolicyUpdate(BaseModel):
    entry: SessionPolicyEntrySchema


class PlatformCompanyUserSummary(BaseModel):
    id: UUID
    email: str
    full_name: str
    is_active: bool
