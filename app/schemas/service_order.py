from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import CostLineCategory, OrderPriority, OrderStatus, ServiceOrderKind


class NextOrderNumberResponse(BaseModel):
    order_number: str
    order_kind: ServiceOrderKind
    site_id: UUID


class ServiceOrderCreate(BaseModel):
    equipment_id: UUID
    current_customer_id: UUID
    original_owner_id: Optional[UUID] = None
    problem_description: str = Field(..., min_length=5)
    order_kind: ServiceOrderKind = ServiceOrderKind.WORKSHOP_INTAKE
    priority: OrderPriority = OrderPriority.MEDIUM
    device_condition_on_entry: Optional[str] = None
    service_contract_id: Optional[UUID] = None
    parent_order_id: Optional[UUID] = None
    portal_submitted_json: Optional[dict[str, Any]] = None
    site_id: UUID
    received_at: Optional[datetime] = None
    received_by_id: Optional[UUID] = None
    customer_po_number: Optional[str] = Field(None, max_length=64)
    sales_area: Optional[str] = Field(None, max_length=120)
    assigned_to_id: Optional[UUID] = None
    estimated_completion: Optional[datetime] = None


class ServiceOrderUpdate(BaseModel):
    priority: Optional[OrderPriority] = None
    assigned_to_id: Optional[UUID] = None
    problem_description: Optional[str] = None
    diagnosis_notes: Optional[str] = None
    estimated_completion: Optional[datetime] = None
    actual_completion: Optional[datetime] = None
    cost_parts: Optional[Decimal] = Field(None, decimal_places=2, ge=0)
    cost_labor: Optional[Decimal] = Field(None, decimal_places=2, ge=0)
    current_customer_id: Optional[UUID] = None
    original_owner_id: Optional[UUID] = None
    site_id: Optional[UUID] = None
    received_at: Optional[datetime] = None
    received_by_id: Optional[UUID] = None
    customer_po_number: Optional[str] = Field(None, max_length=64)
    sales_area: Optional[str] = Field(None, max_length=120)
    device_condition_on_entry: Optional[str] = None
    service_contract_id: Optional[UUID] = None
    parent_order_id: Optional[UUID] = None
    portal_submitted_json: Optional[dict[str, Any]] = None


class ServiceOrderStatusPatch(BaseModel):
    status: OrderStatus
    notes: Optional[str] = None
    time_spent_seconds: Optional[int] = Field(None, ge=0)


class ServiceOrderCostLineCreate(BaseModel):
    category: CostLineCategory
    amount: Decimal = Field(..., decimal_places=2, ge=0)
    description: Optional[str] = Field(None, max_length=255)
    sort_order: int = Field(0, ge=0, le=9999)


class ServiceOrderCostLineUpdate(BaseModel):
    category: Optional[CostLineCategory] = None
    amount: Optional[Decimal] = Field(None, decimal_places=2, ge=0)
    description: Optional[str] = Field(None, max_length=255)
    sort_order: Optional[int] = Field(None, ge=0, le=9999)


class ServiceOrderCostLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    service_order_id: UUID
    category: CostLineCategory
    description: Optional[str]
    amount: Decimal
    sort_order: int
    created_at: datetime


class ServiceOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    order_number: str
    order_kind: ServiceOrderKind
    equipment_id: UUID
    current_customer_id: UUID
    original_owner_id: Optional[UUID]
    status: OrderStatus
    priority: OrderPriority
    assigned_to_id: Optional[UUID]
    problem_description: str
    diagnosis_notes: Optional[str]
    estimated_completion: Optional[datetime]
    actual_completion: Optional[datetime]
    cost_parts: Decimal
    cost_labor: Decimal
    total_cost: Decimal
    created_at: datetime
    updated_at: datetime
    created_by_id: Optional[UUID]
    site_id: Optional[UUID] = None
    received_at: Optional[datetime] = None
    received_by_id: Optional[UUID] = None
    customer_po_number: Optional[str] = None
    sales_area: Optional[str] = None
    device_condition_on_entry: Optional[str] = None
    service_contract_id: Optional[UUID] = None
    parent_order_id: Optional[UUID] = None
    portal_submitted_json: Optional[dict[str, Any]] = None
