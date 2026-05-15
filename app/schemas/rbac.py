from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import RoleChangeStatus, UserRole


class SiteCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    location: Optional[str] = None


class SiteUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    location: Optional[str] = None
    is_active: Optional[bool] = None


class SiteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    name: str
    location: Optional[str]
    is_active: bool
    created_at: datetime


class UserSiteRoleInput(BaseModel):
    site_id: Optional[UUID] = None
    role: UserRole


class UserSiteRoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    site_id: Optional[UUID]
    role: UserRole
    is_active: bool


class UserWithRolesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    is_active: bool
    role: UserRole
    site_roles: list[UserSiteRoleResponse] = Field(default_factory=list)


class EntitlementsLimits(BaseModel):
    max_users: Optional[int] = None
    max_orders_month: Optional[int] = None
    storage_mb: Optional[int] = None


class EntitlementsUsage(BaseModel):
    users: int = 0
    orders_month: int = 0
    storage_mb: int = 0


class EntitlementsPayload(BaseModel):
    plan: str
    status: str
    modules: list[str]
    limits: EntitlementsLimits
    usage: EntitlementsUsage


class MePermissionsResponse(BaseModel):
    role: UserRole
    site_id: Optional[UUID] = None
    permissions: list[str]
    sites: list[SiteResponse]
    entitlements: EntitlementsPayload


class PermissionCheckResponse(BaseModel):
    has_permission: bool
    reason: str = ""


class RoleChangeRequestCreate(BaseModel):
    requested_role: UserRole
    site_id: Optional[UUID] = None
    reason: Optional[str] = None


class RoleChangeRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    site_id: Optional[UUID]
    requested_role: UserRole
    requested_by_id: UUID
    approved_by_id: Optional[UUID]
    status: RoleChangeStatus
    reason: Optional[str]
    created_at: datetime
    updated_at: datetime


class TemporaryPermissionGrant(BaseModel):
    permission: str = Field(..., min_length=3, max_length=80)
    expires_in_days: int = Field(..., ge=1, le=365)
    site_id: Optional[UUID] = None


class TemporaryPermissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    permission: str
    expires_at: datetime
    site_id: Optional[UUID]
    granted_by_id: UUID
    created_at: datetime


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: Optional[UUID]
    company_id: Optional[UUID]
    site_id: Optional[UUID]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    metadata_json: dict[str, Any]
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime
