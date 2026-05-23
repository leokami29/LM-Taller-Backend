from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EquipmentOwnerSummary(BaseModel):
    """Cliente titular del equipo (subset para listados y detalle)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str


class EquipmentAttributeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    equipment_id: UUID
    key: str
    value: str
    type: str


class EquipmentAttributeCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=80)
    value: str = Field(..., min_length=1)
    type: str = Field("text", pattern="^(text|number|date|boolean)$")


class EquipmentAttributeUpdate(BaseModel):
    value: Optional[str] = Field(None, min_length=1)
    type: Optional[str] = Field(None, pattern="^(text|number|date|boolean)$")


class EquipmentCreate(BaseModel):
    serial_number: str = Field(..., min_length=1, max_length=120)
    equipment_type: Optional[str] = Field(None, max_length=120)
    category: Optional[str] = Field(None, max_length=80)
    subcategory: Optional[str] = Field(None, max_length=80)
    brand: Optional[str] = Field(None, max_length=120)
    model: Optional[str] = Field(None, max_length=120)
    manufacturer: Optional[str] = Field(None, max_length=120)
    manufacturer_part_number: Optional[str] = Field(None, max_length=120)
    imei: Optional[str] = Field(None, max_length=32)
    color: Optional[str] = Field(None, max_length=64)
    barcode: Optional[str] = Field(None, max_length=64)
    original_owner_id: Optional[UUID] = None
    status: Optional[str] = Field("available", max_length=20)
    location: Optional[str] = Field(None, max_length=120)
    parent_equipment_id: Optional[UUID] = None
    supplier_id: Optional[UUID] = None
    purchase_date: Optional[date] = None
    purchase_price: Optional[float] = Field(None, ge=0)
    warranty_start: Optional[date] = None
    warranty_end: Optional[date] = None
    warranty_provider: Optional[str] = Field(None, max_length=120)
    photos_urls: list[Any] = Field(default_factory=list)
    image_urls: list[Any] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    additional_notes: Optional[str] = Field(None, max_length=2000)
    first_received_date: Optional[date] = None


class EquipmentUpdate(BaseModel):
    serial_number: Optional[str] = Field(None, min_length=1, max_length=120)
    equipment_type: Optional[str] = Field(None, max_length=120)
    category: Optional[str] = Field(None, max_length=80)
    subcategory: Optional[str] = Field(None, max_length=80)
    brand: Optional[str] = Field(None, max_length=120)
    model: Optional[str] = Field(None, max_length=120)
    manufacturer: Optional[str] = Field(None, max_length=120)
    manufacturer_part_number: Optional[str] = Field(None, max_length=120)
    imei: Optional[str] = Field(None, max_length=32)
    color: Optional[str] = Field(None, max_length=64)
    barcode: Optional[str] = Field(None, max_length=64)
    original_owner_id: Optional[UUID] = None
    status: Optional[str] = Field(None, max_length=20)
    location: Optional[str] = Field(None, max_length=120)
    parent_equipment_id: Optional[UUID] = None
    supplier_id: Optional[UUID] = None
    purchase_date: Optional[date] = None
    purchase_price: Optional[float] = Field(None, ge=0)
    warranty_start: Optional[date] = None
    warranty_end: Optional[date] = None
    warranty_provider: Optional[str] = Field(None, max_length=120)
    photos_urls: Optional[list[Any]] = None
    image_urls: Optional[list[Any]] = None
    tags: Optional[list[str]] = None
    custom_fields: Optional[dict[str, Any]] = None
    additional_notes: Optional[str] = Field(None, max_length=2000)
    first_received_date: Optional[date] = None


class EquipmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    serial_number: str
    equipment_type: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    manufacturer_part_number: Optional[str] = None
    imei: Optional[str] = None
    color: Optional[str] = None
    barcode: Optional[str] = None
    original_owner_id: Optional[UUID] = None
    original_owner: Optional[EquipmentOwnerSummary] = None
    status: Optional[str] = None
    location: Optional[str] = None
    parent_equipment_id: Optional[UUID] = None
    supplier_id: Optional[UUID] = None
    purchase_date: Optional[date] = None
    purchase_price: Optional[float] = None
    warranty_start: Optional[date] = None
    warranty_end: Optional[date] = None
    warranty_provider: Optional[str] = None
    photos_urls: list[Any] = Field(default_factory=list)
    image_urls: list[Any] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    additional_notes: Optional[str] = None
    first_received_date: Optional[date] = None
    created_at: datetime
    updated_at: datetime
    attributes: Optional[list[EquipmentAttributeResponse]] = None

    @field_validator("photos_urls", "image_urls", "tags", mode="before")
    @classmethod
    def _coerce_none_to_list(cls, v):
        return v if v is not None else []

    @field_validator("custom_fields", mode="before")
    @classmethod
    def _coerce_none_to_dict(cls, v):
        return v if v is not None else {}

    @field_validator("attributes", mode="before")
    @classmethod
    def _coerce_none_to_list_attr(cls, v):
        return v if v is not None else []
