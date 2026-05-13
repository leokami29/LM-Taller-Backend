from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EquipmentOwnerSummary(BaseModel):
    """Cliente titular del equipo (subset para listados y detalle)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str


class EquipmentCreate(BaseModel):
    serial_number: str = Field(..., min_length=1, max_length=120)
    equipment_type: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    imei: Optional[str] = None
    color: Optional[str] = None
    original_owner_id: Optional[UUID] = None
    photos_urls: list[Any] = Field(default_factory=list)
    additional_notes: Optional[str] = None
    first_received_date: Optional[date] = None


class EquipmentUpdate(BaseModel):
    serial_number: Optional[str] = Field(None, min_length=1, max_length=120)
    equipment_type: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    imei: Optional[str] = None
    color: Optional[str] = None
    original_owner_id: Optional[UUID] = None
    photos_urls: Optional[list[Any]] = None
    additional_notes: Optional[str] = None
    first_received_date: Optional[date] = None


class EquipmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    serial_number: str
    equipment_type: Optional[str]
    brand: Optional[str]
    model: Optional[str]
    imei: Optional[str]
    color: Optional[str]
    original_owner_id: Optional[UUID]
    original_owner: Optional[EquipmentOwnerSummary] = None
    photos_urls: list[Any]
    additional_notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    first_received_date: Optional[date]
