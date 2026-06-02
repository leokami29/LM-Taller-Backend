from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CompanyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    nit_rut: str = Field(..., min_length=1, max_length=20)
    address: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    currency: str = "COP"

class CompanyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    address: Optional[str] = Field(None, max_length=500)
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    country: Optional[str] = None
    currency: Optional[str] = None
    logo_url: Optional[str] = Field(None, max_length=4096)


class CompanyLogoUpdate(BaseModel):
    logo_url: Optional[str] = Field(None, max_length=4096)
    logo_base64: Optional[str] = None
    mime_type: Optional[str] = Field(None, pattern=r"^image/(png|jpeg|jpg|gif|webp|svg\+xml)$")


class CompanyEmailSettings(BaseModel):
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_name: Optional[str] = None
    smtp_from_email: Optional[str] = None
    smtp_use_tls: bool = True


class CompanyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    nit_rut: str
    address: str
    phone: Optional[str]
    email: Optional[str]
    logo_url: Optional[str] = None
    country: str
    currency: str
    is_active: bool
    created_at: datetime
