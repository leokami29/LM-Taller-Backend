from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.enums import OrderPriority, OrderStatus, ServiceOrderKind
from app.schemas.service_contract import ServiceContractResponse


class PortalLoginRequest(BaseModel):
    email: EmailStr
    password: str
    tenant_slug: Optional[str] = None


class PortalUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    customer_id: UUID
    email: str
    full_name: str
    is_active: bool
    last_login: Optional[datetime] = None


class PortalTokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: PortalUserResponse
    customer_id: UUID


class PortalMeResponse(BaseModel):
    user: PortalUserResponse
    customer_id: UUID
    contracts: list[ServiceContractResponse]


class PortalUserCreate(BaseModel):
    customer_id: UUID
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)


class PortalUserCreateResponse(BaseModel):
    user: PortalUserResponse
    temporary_password: Optional[str] = None


class PortalUserPatch(BaseModel):
    is_active: Optional[bool] = None
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    password: Optional[str] = Field(None, min_length=8, max_length=128)


class PortalOrderCreate(BaseModel):
    service_contract_id: UUID
    order_kind: ServiceOrderKind
    equipment_id: UUID
    problem_description: str = Field(..., min_length=5)
    priority: OrderPriority = OrderPriority.MEDIUM
    customer_po_number: Optional[str] = Field(None, max_length=64)
    portal_submitted_json: Optional[dict[str, Any]] = None


class PortalOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_number: str
    order_kind: ServiceOrderKind
    status: OrderStatus
    priority: OrderPriority
    problem_description: str
    equipment_id: UUID
    service_contract_id: Optional[UUID]
    portal_submitted_json: Optional[dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    estimated_completion: Optional[datetime] = None
