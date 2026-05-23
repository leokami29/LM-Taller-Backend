from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import InventoryMovementType


class InventoryItemCreate(BaseModel):
    item_type: Optional[str] = None
    sku: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = None
    quantity_stock: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=3)
    quantity_minimum: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=3)
    unit_cost: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    unit_price: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    supplier_id: Optional[UUID] = None
    photos_urls: list[Any] = Field(default_factory=list)
    barcode: Optional[str] = None
    weight: Optional[Decimal] = Field(None, ge=0, decimal_places=3)
    dimensions_json: dict[str, Any] = Field(default_factory=dict)


class InventoryItemUpdate(BaseModel):
    item_type: Optional[str] = None
    sku: Optional[str] = Field(None, min_length=1, max_length=80)
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = None
    quantity_minimum: Optional[Decimal] = Field(None, ge=0, decimal_places=3)
    unit_cost: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    unit_price: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    supplier_id: Optional[UUID] = None
    photos_urls: Optional[list[Any]] = None
    barcode: Optional[str] = None
    weight: Optional[Decimal] = Field(None, ge=0, decimal_places=3)
    dimensions_json: Optional[dict[str, Any]] = None


class InventoryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    item_type: Optional[str]
    sku: str
    name: str
    description: Optional[str]
    category: Optional[str]
    quantity_stock: Decimal
    quantity_minimum: Decimal
    unit_cost: Optional[Decimal]
    unit_price: Optional[Decimal]
    supplier_id: Optional[UUID]
    photos_urls: list[Any]
    barcode: Optional[str]
    weight: Optional[Decimal]
    dimensions_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    last_restocked_at: Optional[datetime]


class InventoryStockChange(BaseModel):
    movement_type: InventoryMovementType
    quantity_change: Decimal = Field(..., decimal_places=3)
    service_order_id: Optional[UUID] = None
    notes: Optional[str] = None


class InventoryMovementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    inventory_item_id: UUID
    movement_type: InventoryMovementType
    quantity_change: Decimal
    service_order_id: Optional[UUID]
    notes: Optional[str]
    moved_by_id: Optional[UUID]
    moved_at: datetime


# ─── Inventory Category schemas ───

class InventoryCategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    color: Optional[str] = Field(None, max_length=7)
    description: Optional[str] = Field(None, max_length=255)


class InventoryCategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    color: Optional[str] = Field(None, max_length=7)
    description: Optional[str] = Field(None, max_length=255)


class InventoryCategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    name: str
    color: Optional[str]
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
