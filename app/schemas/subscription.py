from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.core.enums import SubscriptionStatus


class SubscriptionAssign(BaseModel):
    plan_code: str = Field(..., pattern="^(starter|pro|enterprise)$")
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    billing_email: Optional[EmailStr] = None
    current_period_end: Optional[datetime] = None
    entitlements_override_json: dict[str, Any] = Field(default_factory=dict)


class SubscriptionResponse(BaseModel):
    company_id: UUID
    plan_code: str
    status: SubscriptionStatus
    billing_email: Optional[str] = None
    provider: str = "manual"
    current_period_end: Optional[datetime] = None
