from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.permissions import ADMIN_USERS
from app.db.models.sla_policy import SlaPolicy
from app.db.session import get_db
from app.dependencies import PermissionContext, get_permission_context
from app.schemas.common import PaginatedResponse
from app.schemas.sla_policy import (
    SlaPolicyCreate,
    SlaPolicyResponse,
    SlaPolicyUpdate,
)
from app.services.sla_policy_service import (
    create_sla_policy,
    delete_sla_policy,
    update_sla_policy,
)

router = APIRouter(prefix="/sla-policies", tags=["sla-policies"])


def _require_admin(ctx: PermissionContext) -> None:
    if ADMIN_USERS not in ctx.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permiso requerido: {ADMIN_USERS}",
        )


@router.get("/", response_model=PaginatedResponse[SlaPolicyResponse])
def list_sla_policies(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    ctx: PermissionContext = Depends(get_permission_context),
    db: Session = Depends(get_db),
) -> dict:
    q = db.query(SlaPolicy).filter(SlaPolicy.company_id == ctx.company_id)
    total = q.count()
    items = q.order_by(SlaPolicy.created_at.desc()).offset(skip).limit(limit).all()
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.post("/", response_model=SlaPolicyResponse, status_code=status.HTTP_201_CREATED)
def create_sla_policy_endpoint(
    payload: SlaPolicyCreate,
    ctx: PermissionContext = Depends(get_permission_context),
    db: Session = Depends(get_db),
) -> SlaPolicy:
    _require_admin(ctx)
    row = create_sla_policy(
        db,
        company_id=ctx.company_id,
        name=payload.name,
        order_kind=payload.order_kind,
        priority=payload.priority,
        response_time_hours=payload.response_time_hours,
        resolution_time_hours=payload.resolution_time_hours,
        warning_threshold_hours=payload.warning_threshold_hours,
        is_active=payload.is_active,
    )
    db.commit()
    db.refresh(row)
    return row


@router.get("/{policy_id}", response_model=SlaPolicyResponse)
def get_sla_policy(
    policy_id: UUID,
    ctx: PermissionContext = Depends(get_permission_context),
    db: Session = Depends(get_db),
) -> SlaPolicy:
    row = (
        db.query(SlaPolicy)
        .filter(SlaPolicy.id == policy_id, SlaPolicy.company_id == ctx.company_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Política SLA no encontrada")
    return row


@router.put("/{policy_id}", response_model=SlaPolicyResponse)
def update_sla_policy_endpoint(
    policy_id: UUID,
    payload: SlaPolicyUpdate,
    ctx: PermissionContext = Depends(get_permission_context),
    db: Session = Depends(get_db),
) -> SlaPolicy:
    _require_admin(ctx)
    row = (
        db.query(SlaPolicy)
        .filter(SlaPolicy.id == policy_id, SlaPolicy.company_id == ctx.company_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Política SLA no encontrada")
    update_sla_policy(db, row, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sla_policy_endpoint(
    policy_id: UUID,
    ctx: PermissionContext = Depends(get_permission_context),
    db: Session = Depends(get_db),
) -> Response:
    _require_admin(ctx)
    row = (
        db.query(SlaPolicy)
        .filter(SlaPolicy.id == policy_id, SlaPolicy.company_id == ctx.company_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Política SLA no encontrada")
    delete_sla_policy(db, row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
