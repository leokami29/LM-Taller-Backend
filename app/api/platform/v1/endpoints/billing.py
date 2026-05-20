"""Facturación mock por empresa."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.dt import utc_now
from app.core.permissions import PLATFORM_BILLING_READ, PLATFORM_COMPANIES_WRITE
from app.db.catalog.models import BillingEvent, Subscription
from app.db.models.platform_user import PlatformUser
from app.db.session import catalog_session_scope
from app.dependencies import RequirePlatformPermission

router = APIRouter(prefix="/companies", tags=["platform-billing"])

BillingStatus = Literal["paid", "pending", "failed", "waived"]


class BillingEventResponse(BaseModel):
    id: UUID
    company_id: UUID
    subscription_id: UUID | None
    amount_cop: int
    status: str
    period_start: datetime | None
    period_end: datetime | None
    paid_at: datetime | None
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class BillingEventCreate(BaseModel):
    amount_cop: int = Field(ge=0)
    status: BillingStatus = "paid"
    period_start: datetime | None = None
    period_end: datetime | None = None
    paid_at: datetime | None = None
    notes: str | None = None


@router.get("/{company_id}/billing-events", response_model=list[BillingEventResponse])
def list_billing_events(
    company_id: UUID,
    _user: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_BILLING_READ)),
) -> list[BillingEventResponse]:
    with catalog_session_scope() as catalog_db:
        rows = (
            catalog_db.query(BillingEvent)
            .filter(BillingEvent.company_id == company_id)
            .order_by(BillingEvent.created_at.desc())
            .all()
        )
        return [BillingEventResponse.model_validate(r) for r in rows]


@router.post("/{company_id}/billing-events", response_model=BillingEventResponse)
def create_billing_event(
    company_id: UUID,
    payload: BillingEventCreate,
    _user: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_WRITE)),
) -> BillingEventResponse:
    with catalog_session_scope() as catalog_db:
        sub = catalog_db.query(Subscription).filter(Subscription.company_id == company_id).first()
        row = BillingEvent(
            id=uuid4(),
            company_id=company_id,
            subscription_id=sub.id if sub else None,
            amount_cop=payload.amount_cop,
            status=payload.status,
            period_start=payload.period_start,
            period_end=payload.period_end,
            paid_at=payload.paid_at or (utc_now() if payload.status == "paid" else None),
            notes=payload.notes,
        )
        catalog_db.add(row)
        catalog_db.commit()
        catalog_db.refresh(row)
        return BillingEventResponse.model_validate(row)
