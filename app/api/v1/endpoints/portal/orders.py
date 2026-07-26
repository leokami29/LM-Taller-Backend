from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.core.contract_template import validate_submitted_against_template
from app.core.enums import PORTAL_ALLOWED_ORDER_KINDS, OrderStatus
from app.core.exceptions import InvalidOrderTransitionError
from app.db.models.equipment import Equipment
from app.db.models.service_contract import ServiceContract
from app.db.models.service_order import ServiceOrder, ServiceOrderCostLine, ServiceOrderTimeline
from app.db.session import get_db
from app.dependencies import PortalContext, get_portal_context
from app.schemas.common import PaginatedResponse
from app.schemas.portal import PortalOrderCreate, PortalOrderResponse
from app.schemas.service_order import (
    OrderTimelineEntryResponse,
    ServiceOrderCostLineResponse,
)
from app.services.contract_service import contract_is_active, count_contract_orders_this_month
from app.services.order_service import change_order_status, create_service_order
from app.services.permission_service import PermissionService

router = APIRouter(prefix="/orders", tags=["portal-orders"])


@router.get("/", response_model=PaginatedResponse[PortalOrderResponse])
def portal_list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status_filter: Optional[OrderStatus] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    ctx: PortalContext = Depends(get_portal_context),
    db: Session = Depends(get_db),
) -> dict:
    q = db.query(ServiceOrder).filter(
        ServiceOrder.company_id == ctx.company_id,
        ServiceOrder.current_customer_id == ctx.customer_id,
    )
    if status_filter:
        q = q.filter(ServiceOrder.status == status_filter)
    if search:
        term = f"%{search.lower()}%"
        q = q.filter(
            ServiceOrder.order_number.ilike(term) | ServiceOrder.problem_description.ilike(term)
        )
    if date_from:
        q = q.filter(ServiceOrder.created_at >= date_from)
    if date_to:
        q = q.filter(ServiceOrder.created_at <= date_to)
    total = q.count()
    items = (
        q.options(joinedload(ServiceOrder.equipment))
        .order_by(ServiceOrder.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get("/{order_id}", response_model=PortalOrderResponse)
def portal_get_order(
    order_id: UUID,
    ctx: PortalContext = Depends(get_portal_context),
    db: Session = Depends(get_db),
) -> ServiceOrder:
    row = (
        db.query(ServiceOrder)
        .filter(
            ServiceOrder.id == order_id,
            ServiceOrder.company_id == ctx.company_id,
            ServiceOrder.current_customer_id == ctx.customer_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    return row


@router.post("/", response_model=PortalOrderResponse, status_code=status.HTTP_201_CREATED)
def portal_create_order(
    payload: PortalOrderCreate,
    ctx: PortalContext = Depends(get_portal_context),
    db: Session = Depends(get_db),
) -> ServiceOrder:
    if payload.order_kind.value not in PORTAL_ALLOWED_ORDER_KINDS:
        raise HTTPException(status_code=400, detail="Tipo de orden no permitido en portal")

    contract = (
        db.query(ServiceContract)
        .filter(
            ServiceContract.id == payload.service_contract_id,
            ServiceContract.company_id == ctx.company_id,
            ServiceContract.customer_id == ctx.customer_id,
        )
        .first()
    )
    if not contract or not contract_is_active(contract):
        raise HTTPException(status_code=400, detail="Contrato no válido o inactivo")
    if payload.order_kind.value not in (contract.allowed_order_kinds or []):
        raise HTTPException(status_code=400, detail="Este contrato no permite ese tipo de orden")
    if contract.max_orders_per_month:
        used = count_contract_orders_this_month(db, company_id=ctx.company_id, contract_id=contract.id)
        if used >= contract.max_orders_per_month:
            raise HTTPException(status_code=403, detail="Cupo mensual del contrato agotado")

    equipment = (
        db.query(Equipment)
        .filter(Equipment.id == payload.equipment_id, Equipment.company_id == ctx.company_id)
        .first()
    )
    if not equipment:
        raise HTTPException(status_code=400, detail="Equipo no encontrado")
    owns_equipment = equipment.original_owner_id == ctx.customer_id
    if not owns_equipment:
        prior = (
            db.query(ServiceOrder.id)
            .filter(
                ServiceOrder.company_id == ctx.company_id,
                ServiceOrder.equipment_id == equipment.id,
                ServiceOrder.current_customer_id == ctx.customer_id,
            )
            .first()
        )
        owns_equipment = prior is not None
    if not owns_equipment:
        raise HTTPException(status_code=403, detail="Equipo no pertenece a este cliente")

    try:
        submitted = validate_submitted_against_template(
            contract.template_json, payload.portal_submitted_json
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if submitted is None:
        submitted = {}
    submitted["_submitted_by_portal_user_id"] = str(ctx.portal_user_id)

    ok, reason = PermissionService(db).can_create_order(ctx.company_id)
    if not ok:
        raise HTTPException(status_code=403, detail=reason)

    try:
        order = create_service_order(
            db,
            company_id=ctx.company_id,
            equipment_id=payload.equipment_id,
            current_customer_id=ctx.customer_id,
            original_owner_id=None,
            problem_description=payload.problem_description,
            priority=payload.priority,
            created_by_id=None,
            order_kind=payload.order_kind,
            site_id=contract.default_site_id,
            customer_po_number=payload.customer_po_number,
            service_contract_id=contract.id,
            portal_submitted_json=submitted,
        )
        db.commit()
        db.refresh(order)
        return order
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{order_id}/timeline", response_model=list[OrderTimelineEntryResponse])
def portal_get_order_timeline(
    order_id: UUID,
    ctx: PortalContext = Depends(get_portal_context),
    db: Session = Depends(get_db),
) -> list[OrderTimelineEntryResponse]:
    row = (
        db.query(ServiceOrder)
        .filter(
            ServiceOrder.id == order_id,
            ServiceOrder.company_id == ctx.company_id,
            ServiceOrder.current_customer_id == ctx.customer_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    entries = (
        db.query(ServiceOrderTimeline)
        .options(joinedload(ServiceOrderTimeline.changed_by))
        .filter(ServiceOrderTimeline.service_order_id == order_id)
        .order_by(ServiceOrderTimeline.changed_at.desc())
        .all()
    )
    return [
        OrderTimelineEntryResponse(
            id=e.id,
            kind="created" if e.old_status is None else "status_change",
            timestamp=e.changed_at,
            old_status=e.old_status,
            new_status=e.new_status,
            notes=e.notes,
            time_spent_seconds=e.time_spent_seconds,
            changed_by_id=e.changed_by_id,
            changed_by_name=e.changed_by.full_name if e.changed_by else None,
        )
        for e in entries
    ]


@router.get("/{order_id}/cost-lines", response_model=list[ServiceOrderCostLineResponse])
def portal_get_order_cost_lines(
    order_id: UUID,
    ctx: PortalContext = Depends(get_portal_context),
    db: Session = Depends(get_db),
) -> list[ServiceOrderCostLineResponse]:
    row = (
        db.query(ServiceOrder)
        .filter(
            ServiceOrder.id == order_id,
            ServiceOrder.company_id == ctx.company_id,
            ServiceOrder.current_customer_id == ctx.customer_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    return (
        db.query(ServiceOrderCostLine)
        .filter(ServiceOrderCostLine.service_order_id == order_id)
        .order_by(ServiceOrderCostLine.sort_order, ServiceOrderCostLine.created_at)
        .all()
    )


@router.post("/{order_id}/cancel", response_model=PortalOrderResponse)
def portal_cancel_order(
    order_id: UUID,
    ctx: PortalContext = Depends(get_portal_context),
    db: Session = Depends(get_db),
) -> ServiceOrder:
    order = (
        db.query(ServiceOrder)
        .filter(
            ServiceOrder.id == order_id,
            ServiceOrder.company_id == ctx.company_id,
            ServiceOrder.current_customer_id == ctx.customer_id,
        )
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    if order.status in (OrderStatus.DELIVERED, OrderStatus.CANCELLED):
        raise HTTPException(status_code=400, detail="Esta orden no puede ser cancelada")
    try:
        change_order_status(
            db,
            order=order,
            new_status=OrderStatus.CANCELLED,
            changed_by=None,
            notes="Cancelada desde el portal por el cliente",
        )
        db.commit()
        db.refresh(order)
        return order
    except InvalidOrderTransitionError as e:
        raise HTTPException(status_code=400, detail=e.message) from e
