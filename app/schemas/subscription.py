from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.core.enums import SubscriptionStatus
from app.core.subscription_lifecycle import validate_subscription_period_status


class SubscriptionAssign(BaseModel):
    plan_code: str = Field(..., pattern="^(starter|pro|enterprise)$")
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    billing_email: Optional[EmailStr] = None
    current_period_end: Optional[datetime] = None
    entitlements_override_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_period_matches_status(self) -> "SubscriptionAssign":
        validate_subscription_period_status(self.status, self.current_period_end)
        return self


class EffectiveEntitlementsSnapshot(BaseModel):
    modules: list[str] = Field(default_factory=list)
    max_users: Optional[int] = None
    max_orders_month: Optional[int] = None
    storage_mb: Optional[int] = None
    active_seats_limit: Optional[int] = None
    monthly_price_cop: Optional[int] = None


class SubscriptionResponse(BaseModel):
    company_id: UUID
    plan_code: str
    status: SubscriptionStatus
    billing_email: Optional[str] = None
    provider: str = "manual"
    current_period_end: Optional[datetime] = None
    entitlements_override_json: dict[str, Any] = Field(default_factory=dict)
    effective_entitlements: EffectiveEntitlementsSnapshot = Field(
        default_factory=EffectiveEntitlementsSnapshot
    )
