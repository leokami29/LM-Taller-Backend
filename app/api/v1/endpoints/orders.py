from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.enums import OrderPriority, OrderStatus, UserRole
from app.core.exceptions import InvalidOrderTransitionError
from app.dependencies import (
    ensure_not_viewer_for_mutation,
    get_current_admin,
    get_current_technician_or_admin,
    get_current_user,
)
from app.db.models.customer import Customer
from app.db.models.equipment import Equipment
from app.db.models.service_order import ServiceOrder
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.common import PaginatedResponse
from app.schemas.service_order import (
    ServiceOrderCreate,
    ServiceOrderResponse,
    ServiceOrderStatusPatch,
    ServiceOrderUpdate,
)
from app.services.order_service import (
    change_order_status,
    create_service_order,
    recompute_total_cost,
)

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/", response_model=PaginatedResponse[ServiceOrderResponse])
def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status_filter: Optional[OrderStatus] = Query(None, alias="status"),
    priority: Optional[OrderPriority] = Query(None),
    search: Optional[str] = Query(None, description="Número de orden o descripción"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    q = db.query(ServiceOrder).filter(ServiceOrder.company_id == current_user.company_id)
    if status_filter:
        q = q.filter(ServiceOrder.status == status_filter)
    if priority:
        q = q.filter(ServiceOrder.priority == priority)
    if search:
        term = f"%{search.lower()}%"
        q = q.filter(
            or_(ServiceOrder.order_number.ilike(term), ServiceOrder.problem_description.ilike(term))
        )
    total = q.count()
    items = q.order_by(ServiceOrder.created_at.desc()).offset(skip).limit(limit).all()
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.post("/", response_model=ServiceOrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: ServiceOrderCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ServiceOrder:
    ensure_not_viewer_for_mutation(current_user)
    if current_user.role == UserRole.TECHNICIAN:
        raise HTTPException(status_code=403, detail="Los técnicos no pueden crear órdenes")

    try:
        order = create_service_order(
            db,
            company_id=current_user.company_id,
            equipment_id=payload.equipment_id,
            current_customer_id=payload.current_customer_id,
            original_owner_id=payload.original_owner_id,
            problem_description=payload.problem_description,
            priority=payload.priority,
            created_by_id=current_user.id,
            device_condition_on_entry=payload.device_condition_on_entry,
        )
        db.commit()
        db.refresh(order)
        return order
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{order_id}", response_model=ServiceOrderResponse)
def get_order(
    order_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ServiceOrder:
    order = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.id == order_id, ServiceOrder.company_id == current_user.company_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    return order


@router.put("/{order_id}", response_model=ServiceOrderResponse)
def update_order(
    order_id: UUID,
    payload: ServiceOrderUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ServiceOrder:
    ensure_not_viewer_for_mutation(current_user)
    order = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.id == order_id, ServiceOrder.company_id == current_user.company_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    data = payload.model_dump(exclude_unset=True)
    if current_user.role == UserRole.RECEPTION and data.keys() & {
        "assigned_to_id",
        "diagnosis_notes",
        "cost_parts",
        "cost_labor",
    }:
        raise HTTPException(status_code=403, detail="Recepción no puede modificar esos campos")

    if "current_customer_id" in data and data["current_customer_id"]:
        c = (
            db.query(Customer)
            .filter(
                Customer.id == data["current_customer_id"],
                Customer.company_id == current_user.company_id,
            )
            .first()
        )
        if not c:
            raise HTTPException(status_code=400, detail="Cliente no válido")
    if "original_owner_id" in data and data["original_owner_id"]:
        c = (
            db.query(Customer)
            .filter(
                Customer.id == data["original_owner_id"],
                Customer.company_id == current_user.company_id,
            )
            .first()
        )
        if not c:
            raise HTTPException(status_code=400, detail="Propietario original no válido")
    if data.get("assigned_to_id"):
        u = (
            db.query(User)
            .filter(
                User.id == data["assigned_to_id"],
                User.company_id == current_user.company_id,
            )
            .first()
        )
        if not u:
            raise HTTPException(status_code=400, detail="Técnico asignado no válido")

    for k, v in data.items():
        setattr(order, k, v)
    recompute_total_cost(order)
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@router.patch("/{order_id}/status", response_model=ServiceOrderResponse)
def patch_order_status(
    order_id: UUID,
    payload: ServiceOrderStatusPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_technician_or_admin),
) -> ServiceOrder:
    order = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.id == order_id, ServiceOrder.company_id == user.company_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    try:
        change_order_status(
            db,
            order=order,
            new_status=payload.status,
            changed_by=user,
            notes=payload.notes,
            time_spent_seconds=payload.time_spent_seconds,
        )
        recompute_total_cost(order)
        db.commit()
        db.refresh(order)
        return order
    except InvalidOrderTransitionError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


@router.delete("/{order_id}")
def delete_order(
    order_id: UUID,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    order = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.id == order_id, ServiceOrder.company_id == admin.company_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    db.delete(order)
    db.commit()
    return {"message": "Orden eliminada", "status": "success"}
