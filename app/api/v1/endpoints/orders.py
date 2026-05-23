import csv
from datetime import datetime
from decimal import Decimal
from io import StringIO
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.enums import OrderPriority, OrderStatus, ServiceOrderKind, UserRole
from app.core.exceptions import InvalidOrderTransitionError
from app.core.permissions import (
    ORDERS_DELETE,
    ORDERS_READ,
    ORDERS_STATUS,
    ORDERS_WRITE,
)
from app.dependencies import RequirePermission, ensure_not_viewer_for_mutation
from app.db.models.customer import Customer
from app.db.models.rbac import Site
from app.db.models.service_order import ServiceOrder, ServiceOrderCostLine, ServiceOrderTimeline
from app.db.models.service_order_image import ServiceOrderImage
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.common import PaginatedResponse
from app.db.models.inventory import InventoryMovement
from app.schemas.inventory import InventoryMovementResponse
from app.schemas.service_order import (
    ServiceOrderCostLineCreate,
    ServiceOrderCostLineResponse,
    ServiceOrderCostLineUpdate,
    NextOrderNumberResponse,
    ServiceOrderCreate,
    ServiceOrderImageCreate,
    ServiceOrderImageResponse,
    ServiceOrderResponse,
    ServiceOrderStatusPatch,
    OrderTimelineEntryResponse,
    ServiceOrderUpdate,
)
from app.services.permission_service import PermissionService
from app.services.order_pdf_service import generate_order_pdf
from app.services.order_service import (
    add_cost_line,
    change_order_status,
    create_service_order,
    delete_cost_line,
    peek_next_order_number,
    get_cost_line_for_order,
    order_has_cost_lines,
    recompute_total_cost,
    update_cost_line,
)
from app.utils.helpers import apply_allowed_updates

router = APIRouter(prefix="/orders", tags=["orders"])


def _require_non_reception_for_costs(user: User) -> None:
    if user.role == UserRole.RECEPTION:
        raise HTTPException(status_code=403, detail="Recepción no puede modificar costos")


@router.get("/export")
def export_orders(
    status_filter: Optional[OrderStatus] = Query(None, alias="status"),
    order_kind: Optional[ServiceOrderKind] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    current_user: User = Depends(RequirePermission(ORDERS_READ)),
    db: Session = Depends(get_db),
) -> Response:
    q = db.query(ServiceOrder).filter(ServiceOrder.company_id == current_user.company_id)
    if status_filter:
        q = q.filter(ServiceOrder.status == status_filter)
    if order_kind:
        q = q.filter(ServiceOrder.order_kind == order_kind)
    if date_from:
        q = q.filter(ServiceOrder.created_at >= date_from)
    if date_to:
        q = q.filter(ServiceOrder.created_at <= date_to)
    orders = q.order_by(ServiceOrder.created_at.desc()).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "order_number", "order_kind", "status", "priority",
        "customer", "equipment_serial", "problem_description",
        "diagnosis_notes", "cost_parts", "cost_labor", "total_cost",
        "created_at",
    ])
    for order in orders:
        writer.writerow([
            order.order_number,
            order.order_kind.value if order.order_kind else "",
            order.status.value if order.status else "",
            order.priority.value if order.priority else "",
            f"{order.current_customer.first_name} {order.current_customer.last_name}" if order.current_customer else "",
            order.equipment.serial_number if order.equipment else "",
            (order.problem_description or "").replace("\n", " "),
            (order.diagnosis_notes or "").replace("\n", " "),
            float(order.cost_parts or 0),
            float(order.cost_labor or 0),
            float(order.total_cost or 0),
            order.created_at.isoformat() if order.created_at else "",
        ])

    csv_bytes = output.getvalue().encode("utf-8-sig")
    output.close()
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="ordenes.csv"'},
    )


@router.get("/", response_model=PaginatedResponse[ServiceOrderResponse])
def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status_filter: Optional[OrderStatus] = Query(None, alias="status"),
    priority: Optional[OrderPriority] = Query(None),
    order_kind: Optional[ServiceOrderKind] = Query(None),
    search: Optional[str] = Query(None, description="Número de orden o descripción"),
    customer_id: Optional[UUID] = Query(None, description="Filtrar por cliente"),
    equipment_id: Optional[UUID] = Query(None, description="Filtrar por equipo"),
    service_contract_id: Optional[UUID] = Query(None, description="Filtrar por contrato"),
    current_user: User = Depends(RequirePermission(ORDERS_READ)),
    db: Session = Depends(get_db),
) -> dict:
    q = db.query(ServiceOrder).filter(ServiceOrder.company_id == current_user.company_id)
    if status_filter:
        q = q.filter(ServiceOrder.status == status_filter)
    if priority:
        q = q.filter(ServiceOrder.priority == priority)
    if order_kind:
        q = q.filter(ServiceOrder.order_kind == order_kind)
    if customer_id:
        q = q.filter(
            or_(ServiceOrder.current_customer_id == customer_id, ServiceOrder.original_owner_id == customer_id)
        )
    if equipment_id:
        q = q.filter(ServiceOrder.equipment_id == equipment_id)
    if service_contract_id:
        q = q.filter(ServiceOrder.service_contract_id == service_contract_id)
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
    ok, reason = PermissionService(db).can_create_order(current_user.company_id)
    if not ok:
        raise HTTPException(status_code=403, detail=reason)

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
            site_id=payload.site_id,
            received_at=payload.received_at,
            received_by_id=payload.received_by_id,
            customer_po_number=payload.customer_po_number,
            sales_area=payload.sales_area,
            assigned_to_id=payload.assigned_to_id,
            estimated_completion=payload.estimated_completion,
            order_kind=payload.order_kind,
            service_contract_id=payload.service_contract_id,
            parent_order_id=payload.parent_order_id,
        )
        db.commit()
        db.refresh(order)
        return order
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/next-number", response_model=NextOrderNumberResponse)
def get_next_order_number(
    site_id: UUID = Query(...),
    order_kind: ServiceOrderKind = Query(ServiceOrderKind.WORKSHOP_INTAKE),
    current_user: User = Depends(RequirePermission(ORDERS_READ)),
    db: Session = Depends(get_db),
) -> dict:
    try:
        preview = peek_next_order_number(
            db,
            company_id=current_user.company_id,
            site_id=site_id,
            order_kind=order_kind,
        )
        return {"order_number": preview, "order_kind": order_kind, "site_id": site_id}
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
    if data.get("site_id"):
        site = (
            db.query(Site)
            .filter(Site.id == data["site_id"], Site.company_id == current_user.company_id)
            .first()
        )
        if not site:
            raise HTTPException(status_code=400, detail="Sede no válida")
    if data.get("received_by_id"):
        u = (
            db.query(User)
            .filter(
                User.id == data["received_by_id"],
                User.company_id == current_user.company_id,
            )
            .first()
        )
        if not u:
            raise HTTPException(status_code=400, detail="Usuario de recepción no válido")
    received_at = data.get("received_at", order.received_at)
    estimated = data.get("estimated_completion", order.estimated_completion)
    if received_at and estimated and estimated < received_at:
        raise HTTPException(
            status_code=400,
            detail="La fecha prometida no puede ser anterior al ingreso",
        )

    allowed = (
        "priority", "assigned_to_id", "problem_description", "diagnosis_notes",
        "estimated_completion", "actual_completion", "cost_parts", "cost_labor",
        "current_customer_id", "original_owner_id", "site_id", "received_at",
        "received_by_id", "customer_po_number", "sales_area", "device_condition_on_entry",
        "service_contract_id", "parent_order_id", "portal_submitted_json",
    )
    apply_allowed_updates(order, data, allowed)
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


def _timeline_entry_response(entry: ServiceOrderTimeline) -> OrderTimelineEntryResponse:
    kind = "created" if entry.old_status is None else "status_change"
    changed_by = entry.changed_by
    return OrderTimelineEntryResponse(
        id=entry.id,
        kind=kind,
        timestamp=entry.changed_at,
        old_status=entry.old_status,
        new_status=entry.new_status,
        notes=entry.notes,
        time_spent_seconds=entry.time_spent_seconds,
        changed_by_id=entry.changed_by_id,
        changed_by_name=changed_by.full_name if changed_by else None,
    )


@router.get("/{order_id}/timeline", response_model=list[OrderTimelineEntryResponse])
def get_order_timeline(
    order_id: UUID,
    current_user: User = Depends(RequirePermission(ORDERS_READ)),
    db: Session = Depends(get_db),
) -> list[OrderTimelineEntryResponse]:
    order = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.id == order_id, ServiceOrder.company_id == current_user.company_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    entries = (
        db.query(ServiceOrderTimeline)
        .options(joinedload(ServiceOrderTimeline.changed_by))
        .filter(ServiceOrderTimeline.service_order_id == order_id)
        .order_by(ServiceOrderTimeline.changed_at.desc())
        .all()
    )
    return [_timeline_entry_response(e) for e in entries]


@router.get("/{order_id}/parts", response_model=list[InventoryMovementResponse])
def get_order_parts(
    order_id: UUID,
    current_user: User = Depends(RequirePermission(ORDERS_READ)),
    db: Session = Depends(get_db),
) -> list[InventoryMovement]:
    order = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.id == order_id, ServiceOrder.company_id == current_user.company_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    return (
        db.query(InventoryMovement)
        .filter(InventoryMovement.service_order_id == order_id)
        .order_by(InventoryMovement.moved_at.desc())
        .all()
    )


@router.get("/{order_id}/print")
def print_order(
    order_id: UUID,
    current_user: User = Depends(RequirePermission(ORDERS_READ)),
    db: Session = Depends(get_db),
) -> Response:
    order = (
        db.query(ServiceOrder)
        .options(
            joinedload(ServiceOrder.current_customer),
            joinedload(ServiceOrder.equipment),
            joinedload(ServiceOrder.cost_lines),
            joinedload(ServiceOrder.timeline_entries),
        )
        .filter(ServiceOrder.id == order_id, ServiceOrder.company_id == current_user.company_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    pdf_bytes = generate_order_pdf(order)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="orden-{order.order_number}.pdf"'},
    )


@router.get("/{order_id}/images", response_model=list[ServiceOrderImageResponse])
def list_order_images(
    order_id: UUID,
    current_user: User = Depends(RequirePermission(ORDERS_READ)),
    db: Session = Depends(get_db),
) -> list[ServiceOrderImage]:
    order = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.id == order_id, ServiceOrder.company_id == current_user.company_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    return (
        db.query(ServiceOrderImage)
        .filter(ServiceOrderImage.service_order_id == order_id)
        .order_by(ServiceOrderImage.sort_order, ServiceOrderImage.created_at)
        .all()
    )


@router.post(
    "/{order_id}/images",
    response_model=ServiceOrderImageResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_order_image(
    order_id: UUID,
    payload: ServiceOrderImageCreate,
    current_user: User = Depends(RequirePermission(ORDERS_WRITE)),
    db: Session = Depends(get_db),
) -> ServiceOrderImage:
    ensure_not_viewer_for_mutation(current_user)
    order = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.id == order_id, ServiceOrder.company_id == current_user.company_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    image = ServiceOrderImage(
        service_order_id=order_id,
        url=payload.url,
        caption=payload.caption,
        sort_order=payload.sort_order,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return image


@router.delete("/{order_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order_image(
    order_id: UUID,
    image_id: UUID,
    current_user: User = Depends(RequirePermission(ORDERS_WRITE)),
    db: Session = Depends(get_db),
) -> Response:
    ensure_not_viewer_for_mutation(current_user)
    order = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.id == order_id, ServiceOrder.company_id == current_user.company_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    image = (
        db.query(ServiceOrderImage)
        .filter(ServiceOrderImage.id == image_id, ServiceOrderImage.service_order_id == order_id)
        .first()
    )
    if not image:
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    db.delete(image)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

