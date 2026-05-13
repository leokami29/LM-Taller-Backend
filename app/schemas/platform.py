from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.enums import PlatformRole


class PlatformUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    role: PlatformRole
    is_active: bool
    created_at: datetime


class PlatformLoginRequest(BaseModel):
    email: EmailStr
    password: str


class PlatformCompanyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    nit_rut: str = Field(..., min_length=1, max_length=20)
    address: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    country: str = "Colombia"
    currency: str = "COP"
    admin_email: EmailStr
    admin_full_name: str = Field(..., min_length=1, max_length=255)
    admin_password: str = Field(..., min_length=8)
    tenant_slug: Optional[str] = Field(
        default=None,
        description="Obligatorio con USE_TENANT_DATABASE_ROUTING: slug único del taller.",
    )
    tenant_database_url: Optional[str] = Field(
        default=None,
        description="Obligatorio con USE_TENANT_DATABASE_ROUTING: URL del Postgres del taller (vacío ya provisionado).",
    )


class PlatformCompanyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    nit_rut: str
    address: str
    phone: Optional[str]
    email: Optional[str]
    country: str
    currency: str
    is_active: bool
    created_at: datetime


class ImpersonateRequest(BaseModel):
    """Solo super_admin: emite access token tenant-scoped para actuar como empresa."""

    company_id: UUID


class PlatformCompanyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    is_active: Optional[bool] = None
    address: Optional[str] = Field(None, min_length=1)
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
