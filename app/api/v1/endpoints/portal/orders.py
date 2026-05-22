from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.contract_template import validate_submitted_against_template
from app.core.enums import PORTAL_ALLOWED_ORDER_KINDS, ServiceOrderKind
from app.dependencies import PortalContext, get_portal_context
from app.db.models.equipment import Equipment
from app.db.models.service_contract import ServiceContract
from app.db.models.service_order import ServiceOrder
from app.db.session import get_db
from app.schemas.common import PaginatedResponse
from app.schemas.portal import PortalOrderCreate, PortalOrderResponse
from app.services.contract_service import contract_is_active, count_contract_orders_this_month
from app.services.order_service import create_service_order
from app.services.permission_service import PermissionService

router = APIRouter(prefix="/orders", tags=["portal-orders"])


@router.get("/", response_model=PaginatedResponse[PortalOrderResponse])
def portal_list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    ctx: PortalContext = Depends(get_portal_context),
    db: Session = Depends(get_db),
) -> dict:
    q = db.query(ServiceOrder).filter(
        ServiceOrder.company_id == ctx.company_id,
        ServiceOrder.current_customer_id == ctx.customer_id,
    )
    total = q.count()
    items = q.order_by(ServiceOrder.created_at.desc()).offset(skip).limit(limit).all()
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
