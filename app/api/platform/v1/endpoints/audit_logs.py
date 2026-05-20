"""Auditoría de acciones de plataforma."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.permissions import PLATFORM_AUDIT_READ
from app.db.catalog.models import CatalogAuditLog
from app.db.models.platform_user import PlatformUser
from app.db.session import catalog_session_scope
from app.dependencies import RequirePlatformPermission

router = APIRouter(prefix="/audit-logs", tags=["platform-audit"])


class AuditLogResponse(BaseModel):
    id: UUID
    actor_type: str
    actor_id: str | None
    company_id: UUID | None
    action: str
    resource_type: str | None
    resource_id: str | None
    metadata_json: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/", response_model=list[AuditLogResponse])
def list_audit_logs(
    company_id: UUID | None = None,
    action: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    _user: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_AUDIT_READ)),
) -> list[AuditLogResponse]:
    with catalog_session_scope() as catalog_db:
        q = catalog_db.query(CatalogAuditLog).order_by(CatalogAuditLog.created_at.desc())
        if company_id:
            q = q.filter(CatalogAuditLog.company_id == company_id)
        if action:
            q = q.filter(CatalogAuditLog.action == action)
        rows = q.limit(limit).all()
        return [AuditLogResponse.model_validate(r) for r in rows]
