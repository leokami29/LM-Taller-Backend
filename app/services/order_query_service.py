from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Query, Session, joinedload

from app.core.enums import OrderPriority, OrderStatus, ServiceOrderKind
from app.db.models.inventory import InventoryMovement
from app.db.models.service_order import ServiceOrder, ServiceOrderCostLine, ServiceOrderTimeline
from app.db.models.service_order_image import ServiceOrderImage
from app.schemas.service_order import OrderTimelineEntryResponse


@dataclass
class OrderListFilters:
    status: OrderStatus | None = None
    priority: OrderPriority | None = None
    order_kind: ServiceOrderKind | None = None
    search: str | None = None
    customer_id: UUID | None = None
    equipment_id: UUID | None = None
    service_contract_id: UUID | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    site_id: UUID | None = None


def _base_orders_query(db: Session, company_id: UUID) -> Query:
    return db.query(ServiceOrder).filter(ServiceOrder.company_id == company_id)


def _apply_filters(q: Query, filters: OrderListFilters) -> Query:
    if filters.site_id is not None:
        q = q.filter(ServiceOrder.site_id == filters.site_id)
    if filters.status:
        q = q.filter(ServiceOrder.status == filters.status)
    if filters.priority:
        q = q.filter(ServiceOrder.priority == filters.priority)
    if filters.order_kind:
        q = q.filter(ServiceOrder.order_kind == filters.order_kind)
    if filters.customer_id:
        q = q.filter(
            or_(
                ServiceOrder.current_customer_id == filters.customer_id,
                ServiceOrder.original_owner_id == filters.customer_id,
            )
        )
    if filters.equipment_id:
        q = q.filter(ServiceOrder.equipment_id == filters.equipment_id)
    if filters.service_contract_id:
        q = q.filter(ServiceOrder.service_contract_id == filters.service_contract_id)
    if filters.search:
        term = f"%{filters.search.lower()}%"
        q = q.filter(
            or_(ServiceOrder.order_number.ilike(term), ServiceOrder.problem_description.ilike(term))
        )
    if filters.date_from:
        q = q.filter(ServiceOrder.created_at >= filters.date_from)
    if filters.date_to:
        q = q.filter(ServiceOrder.created_at <= filters.date_to)
    return q


def list_orders(
    db: Session,
    *,
    company_id: UUID,
    skip: int,
    limit: int,
    filters: OrderListFilters,
) -> tuple[list[ServiceOrder], int]:
    q = _apply_filters(_base_orders_query(db, company_id), filters)
    total = q.count()
    items = q.order_by(ServiceOrder.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def export_orders_csv(
    db: Session,
    *,
    company_id: UUID,
    filters: OrderListFilters,
) -> bytes:
    q = _apply_filters(_base_orders_query(db, company_id), filters)
    orders = q.order_by(ServiceOrder.created_at.desc()).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "order_number",
        "order_kind",
        "status",
        "priority",
        "customer",
        "equipment_serial",
        "problem_description",
        "diagnosis_notes",
        "cost_parts",
        "cost_labor",
        "total_cost",
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
    return csv_bytes


def get_order(
    db: Session,
    *,
    company_id: UUID,
    order_id: UUID,
    site_id: UUID | None = None,
) -> ServiceOrder | None:
    q = db.query(ServiceOrder).filter(ServiceOrder.id == order_id, ServiceOrder.company_id == company_id)
    if site_id is not None:
        q = q.filter(ServiceOrder.site_id == site_id)
    return q.first()


def get_order_for_print(db: Session, *, company_id: UUID, order_id: UUID) -> ServiceOrder | None:
    return (
        db.query(ServiceOrder)
        .options(
            joinedload(ServiceOrder.company),
            joinedload(ServiceOrder.current_customer),
            joinedload(ServiceOrder.equipment),
            joinedload(ServiceOrder.cost_lines),
            joinedload(ServiceOrder.timeline_entries),
        )
        .filter(ServiceOrder.id == order_id, ServiceOrder.company_id == company_id)
        .first()
    )


def list_cost_lines(db: Session, *, order_id: UUID) -> list[ServiceOrderCostLine]:
    return (
        db.query(ServiceOrderCostLine)
        .filter(ServiceOrderCostLine.service_order_id == order_id)
        .order_by(ServiceOrderCostLine.sort_order, ServiceOrderCostLine.created_at)
        .all()
    )


def timeline_entry_response(entry: ServiceOrderTimeline) -> OrderTimelineEntryResponse:
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


def get_order_timeline(db: Session, *, order_id: UUID) -> list[OrderTimelineEntryResponse]:
    entries = (
        db.query(ServiceOrderTimeline)
        .options(joinedload(ServiceOrderTimeline.changed_by))
        .filter(ServiceOrderTimeline.service_order_id == order_id)
        .order_by(ServiceOrderTimeline.changed_at.desc())
        .all()
    )
    return [timeline_entry_response(e) for e in entries]


def list_order_parts(db: Session, *, order_id: UUID) -> list[InventoryMovement]:
    return (
        db.query(InventoryMovement)
        .filter(InventoryMovement.service_order_id == order_id)
        .order_by(InventoryMovement.moved_at.desc())
        .all()
    )


def list_order_images(db: Session, *, order_id: UUID) -> list[ServiceOrderImage]:
    return (
        db.query(ServiceOrderImage)
        .filter(ServiceOrderImage.service_order_id == order_id)
        .order_by(ServiceOrderImage.sort_order, ServiceOrderImage.created_at)
        .all()
    )


def get_order_image(
    db: Session,
    *,
    order_id: UUID,
    image_id: UUID,
) -> ServiceOrderImage | None:
    return (
        db.query(ServiceOrderImage)
        .filter(ServiceOrderImage.id == image_id, ServiceOrderImage.service_order_id == order_id)
        .first()
    )
