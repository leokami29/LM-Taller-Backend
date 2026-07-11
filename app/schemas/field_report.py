from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import FieldReportStatus


class FieldReportBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    findings: Optional[str] = None
    recommendations: Optional[str] = None
    status: FieldReportStatus = FieldReportStatus.DRAFT
    photos_urls: list[str] = Field(default_factory=list)


class FieldReportCreate(FieldReportBase):
    site_id: Optional[UUID] = None
    order_id: Optional[UUID] = None


class FieldReportUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    findings: Optional[str] = None
    recommendations: Optional[str] = None
    status: Optional[FieldReportStatus] = None
    photos_urls: Optional[list[str]] = None
    site_id: Optional[UUID] = None
    order_id: Optional[UUID] = None


class FieldReportResponse(FieldReportBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    site_id: Optional[UUID]
    order_id: Optional[UUID]
    technician_id: UUID
    created_at: datetime
    updated_at: datetime
