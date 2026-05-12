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
    country: str = "Colombia"
    currency: str = "COP"


class CompanyResponse(BaseModel):
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
