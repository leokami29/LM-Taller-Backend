from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.dt import utc_now
from app.core.enums import OrderPriority, OrderStatus, ServiceOrderKind, UserRole
from app.core.exceptions import InvalidOrderTransitionError
from app.core.permissions import (
    ORDERS_DELETE,
    ORDERS_READ,
    ORDERS_STATUS,
    ORDERS_WRITE,
)
from app.core.tracking_code import ensure_order_tracking_code
from app.db.models.customer import Customer
from app.db.models.rbac import Site
from app.db.models.service_order import ServiceOrder, ServiceOrderCostLine
from app.db.models.service_order_image import ServiceOrderImage
from app.db.models.user import User
from app.db.session import get_db
from app.api.deps.permissions import current_permission_site_id
from app.dependencies import (
    PermissionContext,
    RequirePermission,
    ensure_not_viewer_for_mutation,
    get_permission_context,
)
from app.schemas.common import PaginatedResponse
from app.schemas.inventory import InventoryMovementResponse
from app.schemas.service_order import (
    NextOrderNumberResponse,
    OrderTimelineEntryResponse,
    ServiceOrderCostLineCreate,
    ServiceOrderCostLineResponse,
    ServiceOrderCostLineUpdate,
    ServiceOrderCreate,
    ServiceOrderImageCreate,
    ServiceOrderImageResponse,
    ServiceOrderResponse,
    ServiceOrderStatusPatch,
    ServiceOrderUpdate,
)
from app.services.order_document_registry import (
    auto_generate_delivery_slips,
    auto_generate_intake_slips,
    load_order_for_documents,
)
from app.services.order_document_service import generate_work_order_summary
from app.services.order_query_service import (
    OrderListFilters,
    export_orders_csv,
    get_order,
    get_order_for_print,
    get_order_image,
    get_order_timeline,
    list_cost_lines,
    list_order_images,
    list_order_parts,
    list_orders,
)
from app.services.order_service import (
    add_cost_line,
    change_order_status,
    create_service_order,
    delete_cost_line,
    get_cost_line_for_order,
    order_has_cost_lines,
    peek_next_order_number,
    recompute_total_cost,
    update_cost_line,
)
from app.services.permission_service import PermissionService
from app.services.tracking_urls import resolve_tenant_slug_for_company
from app.utils.helpers import apply_allowed_updates

router = APIRouter(prefix="/orders", tags=["orders"])


def _require_non_reception_for_costs(user: User) -> None:
    if user.role == UserRole.RECEPTION:
        raise HTTPException(status_code=403, detail="Recepción no puede modificar costos")


def _order_or_404(
    db: Session,
    *,
    company_id: UUID,
    order_id: UUID,
    site_id: UUID | None = None,
) -> ServiceOrder:
    scoped_site = site_id if site_id is not None else current_permission_site_id()
    order = get_order(db, company_id=company_id, order_id=order_id, site_id=scoped_site)
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    return order


@router.get("/export")
def export_orders(
    status_filter: Optional[OrderStatus] = Query(None, alias="status"),
    order_kind: Optional[ServiceOrderKind] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    current_user: User = Depends(RequirePermission(ORDERS_READ)),
    ctx: PermissionContext = Depends(get_permission_context),
    db: Session = Depends(get_db),
) -> Response:
    filters = OrderListFilters(
        status=status_filter,
        order_kind=order_kind,
        date_from=date_from,
        date_to=date_to,
        site_id=ctx.site_id,
    )
    csv_bytes = export_orders_csv(db, company_id=current_user.company_id, filters=filters)
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="ordenes.csv"'},
    )


@router.get("/", response_model=PaginatedResponse[ServiceOrderResponse])
def list_orders_endpoint(
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
    ctx: PermissionContext = Depends(get_permission_context),
    db: Session = Depends(get_db),
) -> dict:
    filters = OrderListFilters(
        status=status_filter,
        priority=priority,
        order_kind=order_kind,
        search=search,
        customer_id=customer_id,
        equipment_id=equipment_id,
        service_contract_id=service_contract_id,
        site_id=ctx.site_id,
    )
    items, total = list_orders(
        db,
        company_id=current_user.company_id,
        skip=skip,
        limit=limit,
        filters=filters,
    )
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.post("/", response_model=ServiceOrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: ServiceOrderCreate,
    current_user: User = Depends(RequirePermission(ORDERS_WRITE)),
    ctx: PermissionContext = Depends(get_permission_context),
    db: Session = Depends(get_db),
) -> ServiceOrder:
    ensure_not_viewer_for_mutation(current_user)
    ok, reason = PermissionService(db).can_create_order(current_user.company_id)
    if not ok:
        raise HTTPException(status_code=403, detail=reason)
    site_id = payload.site_id
    if ctx.site_id is not None and site_id != ctx.site_id:
        raise HTTPException(status_code=403, detail="No puede crear órdenes en otra sede")

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
            site_id=site_id,
            received_at=payload.received_at,
            received_by_id=payload.received_by_id,
            customer_po_number=payload.customer_po_number,
            sales_area=payload.sales_area,
            assigned_to_id=payload.assigned_to_id,
            estimated_completion=payload.estimated_completion,
            order_kind=payload.order_kind,
            service_contract_id=payload.service_contract_id,
            parent_order_id=payload.parent_order_id,
            accessories_json=payload.accessories_json,
        )
        db.commit()
        loaded = load_order_for_documents(db, company_id=current_user.company_id, order_id=order.id)
        if loaded:
            auto_generate_intake_slips(db, order=loaded, user=current_user)
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
def get_order_endpoint(
    order_id: UUID,
    current_user: User = Depends(RequirePermission(ORDERS_READ)),
    db: Session = Depends(get_db),
) -> ServiceOrder:
    return _order_or_404(db, company_id=current_user.company_id, order_id=order_id)


@router.get("/{order_id}/cost-lines", response_model=list[ServiceOrderCostLineResponse])
def list_order_cost_lines(
    order_id: UUID,
    current_user: User = Depends(RequirePermission(ORDERS_READ)),
    db: Session = Depends(get_db),
) -> list[ServiceOrderCostLine]:
    _order_or_404(db, company_id=current_user.company_id, order_id=order_id)
    return list_cost_lines(db, order_id=order_id)


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
    order = _order_or_404(db, company_id=current_user.company_id, order_id=order_id)
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
    order = _order_or_404(db, company_id=current_user.company_id, order_id=order_id)
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
    order = _order_or_404(db, company_id=current_user.company_id, order_id=order_id)
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
    order = _order_or_404(db, company_id=current_user.company_id, order_id=order_id)

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
            detail=(
                "La orden tiene líneas de costo; gestiona el desglose o elimina las líneas "
                "antes de editar totales aquí."
            ),
        )

    if "current_customer_id" in data and data["current_customer_id"]:
        c = (
            db.query(Customer)
            .filter(Customer.id == data["current_customer_id"], Customer.company_id == current_user.company_id)
            .first()
        )
        if not c:
            raise HTTPException(status_code=400, detail="Cliente no válido")
    if "original_owner_id" in data and data["original_owner_id"]:
        c = (
            db.query(Customer)
            .filter(Customer.id == data["original_owner_id"], Customer.company_id == current_user.company_id)
            .first()
        )
        if not c:
            raise HTTPException(status_code=400, detail="Propietario original no válido")
    if data.get("assigned_to_id"):
        u = (
            db.query(User)
            .filter(User.id == data["assigned_to_id"], User.company_id == current_user.company_id)
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
            .filter(User.id == data["received_by_id"], User.company_id == current_user.company_id)
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
        "priority",
        "assigned_to_id",
        "problem_description",
        "diagnosis_notes",
        "estimated_completion",
        "actual_completion",
        "cost_parts",
        "cost_labor",
        "current_customer_id",
        "original_owner_id",
        "site_id",
        "received_at",
        "received_by_id",
        "customer_po_number",
        "sales_area",
        "device_condition_on_entry",
        "service_contract_id",
        "parent_order_id",
        "portal_submitted_json",
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
    order = _order_or_404(db, company_id=user.company_id, order_id=order_id)
    try:
        change_order_status(
            db,
            order=order,
            new_status=payload.status,
            changed_by=user,
            notes=payload.notes,
            time_spent_seconds=payload.time_spent_seconds,
        )
        if payload.status == OrderStatus.DELIVERED:
            if not order.actual_completion:
                order.actual_completion = utc_now()
            loaded = load_order_for_documents(db, company_id=user.company_id, order_id=order.id)
            if loaded:
                auto_generate_delivery_slips(db, order=loaded, user=user)
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
    order = _order_or_404(db, company_id=current_user.company_id, order_id=order_id)
    db.delete(order)
    db.commit()
    return {"message": "Orden eliminada", "status": "success"}


@router.get("/{order_id}/timeline", response_model=list[OrderTimelineEntryResponse])
def get_order_timeline_endpoint(
    order_id: UUID,
    current_user: User = Depends(RequirePermission(ORDERS_READ)),
    db: Session = Depends(get_db),
) -> list[OrderTimelineEntryResponse]:
    _order_or_404(db, company_id=current_user.company_id, order_id=order_id)
    return get_order_timeline(db, order_id=order_id)


@router.get("/{order_id}/parts", response_model=list[InventoryMovementResponse])
def get_order_parts(
    order_id: UUID,
    current_user: User = Depends(RequirePermission(ORDERS_READ)),
    db: Session = Depends(get_db),
):
    _order_or_404(db, company_id=current_user.company_id, order_id=order_id)
    return list_order_parts(db, order_id=order_id)


@router.get("/{order_id}/print")
def print_order(
    order_id: UUID,
    current_user: User = Depends(RequirePermission(ORDERS_READ)),
    db: Session = Depends(get_db),
) -> Response:
    order = get_order_for_print(db, company_id=current_user.company_id, order_id=order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    ensure_order_tracking_code(db, order)
    tenant_slug = resolve_tenant_slug_for_company(order.company_id)
    pdf_bytes = generate_work_order_summary(order, tenant_slug=tenant_slug)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="orden-{order.order_number}.pdf"'},
    )


@router.get("/{order_id}/images", response_model=list[ServiceOrderImageResponse])
def list_order_images_endpoint(
    order_id: UUID,
    current_user: User = Depends(RequirePermission(ORDERS_READ)),
    db: Session = Depends(get_db),
) -> list[ServiceOrderImage]:
    _order_or_404(db, company_id=current_user.company_id, order_id=order_id)
    return list_order_images(db, order_id=order_id)


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
    _order_or_404(db, company_id=current_user.company_id, order_id=order_id)
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
    _order_or_404(db, company_id=current_user.company_id, order_id=order_id)
    image = get_order_image(db, order_id=order_id, image_id=image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    db.delete(image)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
