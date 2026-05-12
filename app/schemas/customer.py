from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.enums import IdentificationType


class CustomerCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=120)
    last_name: str = Field(..., min_length=1, max_length=120)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    identification_type: Optional[IdentificationType] = None
    identification_number: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CustomerUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=120)
    last_name: Optional[str] = Field(None, min_length=1, max_length=120)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    identification_type: Optional[IdentificationType] = None
    identification_number: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    metadata_json: Optional[dict[str, Any]] = None


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    first_name: str
    last_name: str
    email: Optional[str]
    phone: Optional[str]
    address: Optional[str]
    identification_type: Optional[IdentificationType]
    identification_number: Optional[str]
    city: Optional[str]
    country: Optional[str]
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
