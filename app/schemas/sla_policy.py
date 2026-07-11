from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import OrderPriority, ServiceOrderKind


class SlaPolicyBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    order_kind: Optional[ServiceOrderKind] = None
    priority: Optional[OrderPriority] = None
    response_time_hours: Optional[int] = Field(None, ge=0)
    resolution_time_hours: Optional[int] = Field(None, ge=0)
    warning_threshold_hours: int = Field(6, ge=0)
    is_active: bool = True


class SlaPolicyCreate(SlaPolicyBase):
    pass


class SlaPolicyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    order_kind: Optional[ServiceOrderKind] = None
    priority: Optional[OrderPriority] = None
    response_time_hours: Optional[int] = Field(None, ge=0)
    resolution_time_hours: Optional[int] = Field(None, ge=0)
    warning_threshold_hours: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None


class SlaPolicyResponse(SlaPolicyBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    created_at: datetime
    updated_at: datetime
