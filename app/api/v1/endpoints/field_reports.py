from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.permissions import ORDERS_READ, ORDERS_WRITE
from app.db.models.field_report import FieldReport
from app.db.session import get_db
from app.dependencies import PermissionContext, get_permission_context
from app.schemas.common import PaginatedResponse
from app.schemas.field_report import (
    FieldReportCreate,
    FieldReportResponse,
    FieldReportUpdate,
)
from app.services.field_report_service import (
    create_field_report,
    delete_field_report,
    update_field_report,
)

router = APIRouter(prefix="/field-reports", tags=["field-reports"])


@router.get("/", response_model=PaginatedResponse[FieldReportResponse])
def list_field_reports(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    order_id: Optional[UUID] = Query(None),
    ctx: PermissionContext = Depends(get_permission_context),
    db: Session = Depends(get_db),
) -> dict:
    if ORDERS_READ not in ctx.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permiso requerido: {ORDERS_READ}")
    q = db.query(FieldReport).filter(FieldReport.company_id == ctx.company_id)
    if order_id:
        q = q.filter(FieldReport.order_id == order_id)
    total = q.count()
    items = q.order_by(FieldReport.created_at.desc()).offset(skip).limit(limit).all()
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.post("/", response_model=FieldReportResponse, status_code=status.HTTP_201_CREATED)
def create_field_report_endpoint(
    payload: FieldReportCreate,
    ctx: PermissionContext = Depends(get_permission_context),
    db: Session = Depends(get_db),
) -> FieldReport:
    if ORDERS_WRITE not in ctx.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permiso requerido: {ORDERS_WRITE}")
    row = create_field_report(
        db,
        company_id=ctx.company_id,
        technician_id=ctx.user_id,
        title=payload.title,
        site_id=payload.site_id,
        order_id=payload.order_id,
        findings=payload.findings,
        recommendations=payload.recommendations,
        status=payload.status,
        photos_urls=payload.photos_urls,
    )
    db.commit()
    db.refresh(row)
    return row


@router.get("/{report_id}", response_model=FieldReportResponse)
def get_field_report(
    report_id: UUID,
    ctx: PermissionContext = Depends(get_permission_context),
    db: Session = Depends(get_db),
) -> FieldReport:
    if ORDERS_READ not in ctx.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permiso requerido: {ORDERS_READ}")
    row = (
        db.query(FieldReport)
        .filter(FieldReport.id == report_id, FieldReport.company_id == ctx.company_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    return row


@router.put("/{report_id}", response_model=FieldReportResponse)
def update_field_report_endpoint(
    report_id: UUID,
    payload: FieldReportUpdate,
    ctx: PermissionContext = Depends(get_permission_context),
    db: Session = Depends(get_db),
) -> FieldReport:
    if ORDERS_WRITE not in ctx.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permiso requerido: {ORDERS_WRITE}")
    row = (
        db.query(FieldReport)
        .filter(FieldReport.id == report_id, FieldReport.company_id == ctx.company_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    update_field_report(db, row, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_field_report_endpoint(
    report_id: UUID,
    ctx: PermissionContext = Depends(get_permission_context),
    db: Session = Depends(get_db),
) -> Response:
    if ORDERS_WRITE not in ctx.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permiso requerido: {ORDERS_WRITE}")
    row = (
        db.query(FieldReport)
        .filter(FieldReport.id == report_id, FieldReport.company_id == ctx.company_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    delete_field_report(db, row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
