from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import ContractKind, ServiceOrderKind


class ServiceContractBase(BaseModel):
    customer_id: UUID
    contract_number: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    contract_kind: ContractKind = ContractKind.CUSTOM
    default_site_id: UUID
    allowed_order_kinds: list[ServiceOrderKind] = Field(..., min_length=1)
    template_json: dict[str, Any] = Field(default_factory=dict)
    max_orders_per_month: Optional[int] = Field(None, ge=1)
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    is_active: bool = True


class ServiceContractCreate(ServiceContractBase):
    pass


class ServiceContractUpdate(BaseModel):
    contract_number: Optional[str] = Field(None, min_length=1, max_length=64)
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    contract_kind: Optional[ContractKind] = None
    default_site_id: Optional[UUID] = None
    allowed_order_kinds: Optional[list[ServiceOrderKind]] = None
    template_json: Optional[dict[str, Any]] = None
    max_orders_per_month: Optional[int] = Field(None, ge=1)
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    is_active: Optional[bool] = None


class ServiceContractResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    customer_id: UUID
    contract_number: str
    name: str
    contract_kind: ContractKind
    default_site_id: UUID
    allowed_order_kinds: list[str]
    template_json: dict[str, Any]
    max_orders_per_month: Optional[int]
    valid_from: Optional[date]
    valid_to: Optional[date]
    is_active: bool
    created_at: datetime
    updated_at: datetime
