from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class LicenseLimitsSchema(BaseModel):
    max_users: int | None = None
    max_orders_month: int | None = None
    storage_mb: int | None = None


class LicenseManifestPayload(BaseModel):
    company_id: UUID
    tenant_slug: str
    plan: str
    subscription_status: str
    subscription_usable: bool
    subscription_block_reason: Literal["status", "period_expired"] | None = None
    current_period_end: datetime | None = None
    offline_grace_days: int
    max_days_without_sync: int
    license_valid_until: datetime
    seat_id: UUID
    installation_id: str
    active_seats_limit: int
    server_time: datetime
    config_revision: int = 0
    global_config_revision: int = 0
    modules: list[str] = Field(default_factory=list)
    limits: LicenseLimitsSchema = Field(default_factory=LicenseLimitsSchema)
    issued_at: datetime
    issuer: str = "sgtaller-cloud"
    key_id: str = "v1"


class SignedLicenseManifest(BaseModel):
    manifest: LicenseManifestPayload
    signature: str


class LicenseStatusResponse(BaseModel):
    config_revision: int
    global_config_revision: int
    subscription_status: str
    subscription_usable: bool
    license_valid_until: datetime | None = None
    seat_revoked: bool = False


class DesktopActivateRequest(BaseModel):
    installation_id: str = Field(..., min_length=8, max_length=128)
    hostname: str | None = Field(default=None, max_length=255)


class TenantInstallationResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    company_id: UUID
    installation_id: str
    hostname: str | None
    activated_at: datetime
    last_seen_at: datetime
    revoked_at: datetime | None
