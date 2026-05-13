from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.audit_log import AuditLog


def write_audit(
    db: Session,
    *,
    actor_type: str,
    actor_id: str,
    action: str,
    company_id: Optional[UUID] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    metadata_json: Optional[dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    detail: Optional[str] = None,
) -> None:
    row = AuditLog(
        actor_type=actor_type,
        actor_id=actor_id,
        company_id=company_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata_json=metadata_json or {},
        ip_address=ip_address,
        detail=detail,
    )
    db.add(row)
