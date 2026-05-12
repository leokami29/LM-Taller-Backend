from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import OrderPriority, OrderStatus


class ServiceOrderCreate(BaseModel):
    equipment_id: UUID
    current_customer_id: UUID
    original_owner_id: Optional[UUID] = None
    problem_description: str
    priority: OrderPriority = OrderPriority.MEDIUM
    device_condition_on_entry: Optional[str] = None  # puede mapearse a diagnosis_notes o campo futuro


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


class ServiceOrderStatusPatch(BaseModel):
    status: OrderStatus
    notes: Optional[str] = None
    time_spent_seconds: Optional[int] = Field(None, ge=0)


class ServiceOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    order_number: str
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
