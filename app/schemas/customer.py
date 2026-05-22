from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.enums import IdentificationType
from app.core.rut import validate_rut_field


def _strip_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _normalize_rut(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip().upper()
    return stripped if stripped else None


class _CustomerRutValidationMixin(BaseModel):
    identification_type: Optional[IdentificationType] = None
    identification_number: Optional[str] = Field(None, max_length=80)
    rut: Optional[str] = Field(None, max_length=20)

    @model_validator(mode="after")
    def validate_rut_fields(self) -> "_CustomerRutValidationMixin":
        if self.rut:
            self.rut = validate_rut_field(self.rut)
        if self.identification_type == IdentificationType.RUT and self.identification_number:
            self.identification_number = validate_rut_field(self.identification_number, required=True)
        return self


class CustomerCreate(_CustomerRutValidationMixin):
    first_name: str = Field(..., min_length=1, max_length=120)
    last_name: str = Field(..., min_length=1, max_length=120)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=40)
    address: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=120)
    country: Optional[str] = Field(None, max_length=80)
    notes: Optional[str] = Field(None, max_length=2000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "phone",
        "address",
        "identification_number",
        "city",
        "country",
        "notes",
        mode="before",
    )
    @classmethod
    def strip_text_fields(cls, value: Optional[str]) -> Optional[str]:
        return _strip_optional(value)

    @field_validator("rut", mode="before")
    @classmethod
    def normalize_rut(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_rut(value)


class CustomerUpdate(_CustomerRutValidationMixin):
    first_name: Optional[str] = Field(None, min_length=1, max_length=120)
    last_name: Optional[str] = Field(None, min_length=1, max_length=120)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=40)
    address: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=120)
    country: Optional[str] = Field(None, max_length=80)
    notes: Optional[str] = Field(None, max_length=2000)
    metadata_json: Optional[dict[str, Any]] = None

    @field_validator(
        "phone",
        "address",
        "identification_number",
        "city",
        "country",
        "notes",
        mode="before",
    )
    @classmethod
    def strip_text_fields(cls, value: Optional[str]) -> Optional[str]:
        return _strip_optional(value)

    @field_validator("rut", mode="before")
    @classmethod
    def normalize_rut(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_rut(value)


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
    rut: Optional[str]
    city: Optional[str]
    country: Optional[str]
    notes: Optional[str]
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
