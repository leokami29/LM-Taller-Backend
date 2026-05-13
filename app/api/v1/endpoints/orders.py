from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.enums import OrderPriority, OrderStatus, UserRole
from app.core.exceptions import InvalidOrderTransitionError
from app.core.permissions import (
    ORDERS_DELETE,
    ORDERS_READ,
    ORDERS_STATUS,
    ORDERS_WRITE,
)
from app.dependencies import RequirePermission, ensure_not_viewer_for_mutation
from app.db.models.customer import Customer
from app.db.models.service_order import ServiceOrder, ServiceOrderCostLine
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.common import PaginatedResponse
from app.schemas.service_order import (
    ServiceOrderCostLineCreate,
    ServiceOrderCostLineResponse,
    ServiceOrderCostLineUpdate,
    ServiceOrderCreate,
    ServiceOrderResponse,
    ServiceOrderStatusPatch,
    ServiceOrderUpdate,
)
from app.services.order_service import (
    add_cost_line,
    change_order_status,
    create_service_order,
    delete_cost_line,
    get_cost_line_for_order,
    order_has_cost_lines,
    recompute_total_cost,
    update_cost_line,
)

router = APIRouter(prefix="/orders", tags=["orders"])


def _require_non_reception_for_costs(user: User) -> None:
    if user.role == UserRole.RECEPTION:
        raise HTTPException(status_code=403, detail="Recepción no puede modificar costos")


@router.get("/", response_model=PaginatedResponse[ServiceOrderResponse])
def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status_filter: Optional[OrderStatus] = Query(None, alias="status"),
    priority: Optional[OrderPriority] = Query(None),
    search: Optional[str] = Query(None, description="Número de orden o descripción"),
    current_user: User = Depends(RequirePermission(ORDERS_READ)),
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
    current_user: User = Depends(RequirePermission(ORDERS_WRITE)),
    db: Session = Depends(get_db),
) -> ServiceOrder:
    ensure_not_viewer_for_mutation(current_user)

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
    current_user: User = Depends(RequirePermission(ORDERS_READ)),
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


@router.get("/{order_id}/cost-lines", response_model=list[ServiceOrderCostLineResponse])
def list_order_cost_lines(
    order_id: UUID,
    current_user: User = Depends(RequirePermission(ORDERS_READ)),
    db: Session = Depends(get_db),
) -> list[ServiceOrderCostLine]:
    order = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.id == order_id, ServiceOrder.company_id == current_user.company_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    return (
        db.query(ServiceOrderCostLine)
        .filter(ServiceOrderCostLine.service_order_id == order_id)
        .order_by(ServiceOrderCostLine.sort_order, ServiceOrderCostLine.created_at)
        .all()
    )


@router.post(
    "/{order_id}/cost-lines",
    response_model=ServiceOrderCostLineResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_order_cost_line(
    order_id: UUID,
    payload: ServiceOrderCostLineCreate,
    current_user: User = Depends(RequirePermission(ORDERS_WRITE)),
    db: Session = Depends(get_db),
) -> ServiceOrderCostLine:
    ensure_not_viewer_for_mutation(current_user)
    _require_non_reception_for_costs(current_user)
    order = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.id == order_id, ServiceOrder.company_id == current_user.company_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    line = add_cost_line(
        db,
        order=order,
        category=payload.category,
        amount=Decimal(payload.amount),
        description=payload.description,
        sort_order=payload.sort_order,
    )
    db.commit()
    db.refresh(line)
    return line


@router.put("/{order_id}/cost-lines/{line_id}", response_model=ServiceOrderCostLineResponse)
def update_order_cost_line(
    order_id: UUID,
    line_id: UUID,
    payload: ServiceOrderCostLineUpdate,
    current_user: User = Depends(RequirePermission(ORDERS_WRITE)),
    db: Session = Depends(get_db),
) -> ServiceOrderCostLine:
    ensure_not_viewer_for_mutation(current_user)
    _require_non_reception_for_costs(current_user)
    order = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.id == order_id, ServiceOrder.company_id == current_user.company_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    line = get_cost_line_for_order(db, company_id=current_user.company_id, order_id=order_id, line_id=line_id)
    if not line:
        raise HTTPException(status_code=404, detail="Línea de costo no encontrada")
    data = payload.model_dump(exclude_unset=True)
    line = update_cost_line(
        db,
        order=order,
        line=line,
        category=data.get("category"),
        amount=Decimal(data["amount"]) if "amount" in data else None,
        description=data.get("description"),
        sort_order=data.get("sort_order"),
    )
    db.commit()
    db.refresh(line)
    return line


@router.delete("/{order_id}/cost-lines/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order_cost_line(
    order_id: UUID,
    line_id: UUID,
    current_user: User = Depends(RequirePermission(ORDERS_WRITE)),
    db: Session = Depends(get_db),
) -> Response:
    ensure_not_viewer_for_mutation(current_user)
    _require_non_reception_for_costs(current_user)
    order = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.id == order_id, ServiceOrder.company_id == current_user.company_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    line = get_cost_line_for_order(db, company_id=current_user.company_id, order_id=order_id, line_id=line_id)
    if not line:
        raise HTTPException(status_code=404, detail="Línea de costo no encontrada")
    delete_cost_line(db, order=order, line=line)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{order_id}", response_model=ServiceOrderResponse)
def update_order(
    order_id: UUID,
    payload: ServiceOrderUpdate,
    current_user: User = Depends(RequirePermission(ORDERS_WRITE)),
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

    if order_has_cost_lines(db, order.id) and {"cost_parts", "cost_labor"} & data.keys():
        raise HTTPException(
            status_code=400,
            detail="La orden tiene líneas de costo; gestiona el desglose o elimina las líneas antes de editar totales aquí.",
        )

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
    recompute_total_cost(db, order)
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@router.patch("/{order_id}/status", response_model=ServiceOrderResponse)
def patch_order_status(
    order_id: UUID,
    payload: ServiceOrderStatusPatch,
    db: Session = Depends(get_db),
    user: User = Depends(RequirePermission(ORDERS_STATUS)),
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
        db.commit()
        db.refresh(order)
        return order
    except InvalidOrderTransitionError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


@router.delete("/{order_id}")
def delete_order(
    order_id: UUID,
    current_user: User = Depends(RequirePermission(ORDERS_DELETE)),
    db: Session = Depends(get_db),
) -> dict:
    order = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.id == order_id, ServiceOrder.company_id == current_user.company_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    db.delete(order)
    db.commit()
    return {"message": "Orden eliminada", "status": "success"}
