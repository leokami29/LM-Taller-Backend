from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.dt import utc_now
from app.core.enums import CostLineCategory, OrderStatus
from app.core.exceptions import InvalidOrderTransitionError
from app.db.models.company import Company
from app.db.models.customer import Customer
from app.db.models.equipment import Equipment
from app.db.models.rbac import Site
from app.db.models.service_order import ServiceOrder, ServiceOrderCostLine, ServiceOrderTimeline
from app.db.models.user import User

ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.RECEIVED: {OrderStatus.DIAGNOSING, OrderStatus.CANCELLED},
    OrderStatus.DIAGNOSING: {OrderStatus.WAITING_PARTS, OrderStatus.IN_REPAIR, OrderStatus.CANCELLED},
    OrderStatus.WAITING_PARTS: {OrderStatus.IN_REPAIR, OrderStatus.CANCELLED},
    OrderStatus.IN_REPAIR: {OrderStatus.WAITING_PARTS, OrderStatus.COMPLETED, OrderStatus.CANCELLED},
    OrderStatus.COMPLETED: {OrderStatus.DELIVERED, OrderStatus.CANCELLED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}


def order_has_cost_lines(db: Session, order_id) -> bool:
    return (
        db.query(ServiceOrderCostLine.id)
        .filter(ServiceOrderCostLine.service_order_id == order_id)
        .limit(1)
        .first()
        is not None
    )


def recompute_total_cost(db: Session, order: ServiceOrder) -> None:
    """Sincroniza cost_parts, cost_labor y total_cost desde líneas o desde campos sueltos."""
    lines = (
        db.query(ServiceOrderCostLine)
        .filter(ServiceOrderCostLine.service_order_id == order.id)
        .order_by(ServiceOrderCostLine.sort_order, ServiceOrderCostLine.created_at)
        .all()
    )
    if not lines:
        parts = order.cost_parts or Decimal("0")
        labor = order.cost_labor or Decimal("0")
        order.total_cost = Decimal(parts) + Decimal(labor)
        return

    parts = Decimal("0")
    labor = Decimal("0")
    other = Decimal("0")
    for line in lines:
        amt = line.amount or Decimal("0")
        if line.category == CostLineCategory.PARTS:
            parts += amt
        elif line.category == CostLineCategory.LABOR:
            labor += amt
        else:
            other += amt
    order.cost_parts = parts
    order.cost_labor = labor
    order.total_cost = parts + labor + other


def allocate_order_number(db: Session, company_id) -> str:
    company = (
        db.query(Company)
        .filter(Company.id == company_id)
        .with_for_update()
        .one()
    )
    n = int(company.next_order_number)
    order_number = f"ORD-{n:06d}"
    company.next_order_number = n + 1
    db.add(company)
    return order_number


def assert_transition_allowed(current: OrderStatus, new: OrderStatus) -> None:
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if new not in allowed:
        raise InvalidOrderTransitionError(
            f"No se puede pasar de {current.value} a {new.value}"
        )


def _assert_company_user(db: Session, *, company_id, user_id) -> User:
    user = (
        db.query(User)
        .filter(User.id == user_id, User.company_id == company_id, User.is_active.is_(True))
        .first()
    )
    if not user:
        raise ValueError("Usuario no válido para esta empresa")
    return user


def _assert_company_site(db: Session, *, company_id, site_id) -> Site:
    site = (
        db.query(Site)
        .filter(Site.id == site_id, Site.company_id == company_id, Site.is_active.is_(True))
        .first()
    )
    if not site:
        raise ValueError("Sede no válida")
    return site


def create_service_order(
    db: Session,
    *,
    company_id,
    equipment_id,
    current_customer_id,
    original_owner_id,
    problem_description: str,
    priority,
    created_by_id,
    device_condition_on_entry: Optional[str] = None,
    site_id: Optional[UUID] = None,
    received_at: Optional[datetime] = None,
    received_by_id: Optional[UUID] = None,
    customer_po_number: Optional[str] = None,
    sales_area: Optional[str] = None,
    assigned_to_id: Optional[UUID] = None,
    estimated_completion: Optional[datetime] = None,
) -> ServiceOrder:
    equipment = (
        db.query(Equipment)
        .filter(Equipment.id == equipment_id, Equipment.company_id == company_id)
        .first()
    )
    if not equipment:
        raise ValueError("Equipo no encontrado")

    customer = (
        db.query(Customer)
        .filter(Customer.id == current_customer_id, Customer.company_id == company_id)
        .first()
    )
    if not customer:
        raise ValueError("Cliente no encontrado")

    if original_owner_id:
        oo = (
            db.query(Customer)
            .filter(Customer.id == original_owner_id, Customer.company_id == company_id)
            .first()
        )
        if not oo:
            raise ValueError("Propietario original no encontrado")

    if site_id:
        _assert_company_site(db, company_id=company_id, site_id=site_id)

    reception_user_id = received_by_id or created_by_id
    if reception_user_id:
        _assert_company_user(db, company_id=company_id, user_id=reception_user_id)

    if assigned_to_id:
        _assert_company_user(db, company_id=company_id, user_id=assigned_to_id)

    intake_at = received_at or utc_now()
    if estimated_completion and estimated_completion < intake_at:
        raise ValueError("La fecha prometida no puede ser anterior al ingreso")

    order_number = allocate_order_number(db, company_id)

    order = ServiceOrder(
        company_id=company_id,
        order_number=order_number,
        equipment_id=equipment_id,
        current_customer_id=current_customer_id,
        original_owner_id=original_owner_id,
        status=OrderStatus.RECEIVED,
        priority=priority,
        problem_description=problem_description,
        device_condition_on_entry=device_condition_on_entry,
        cost_parts=Decimal("0"),
        cost_labor=Decimal("0"),
        total_cost=Decimal("0"),
        created_by_id=created_by_id,
        site_id=site_id,
        received_at=intake_at,
        received_by_id=reception_user_id,
        customer_po_number=(customer_po_number or "").strip() or None,
        sales_area=(sales_area or "").strip() or None,
        assigned_to_id=assigned_to_id,
        estimated_completion=estimated_completion,
    )
    recompute_total_cost(db, order)
    db.add(order)
    db.flush()

    timeline = ServiceOrderTimeline(
        service_order_id=order.id,
        old_status=None,
        new_status=OrderStatus.RECEIVED.value,
        changed_by_id=created_by_id,
        notes="Orden creada",
    )
    db.add(timeline)
    return order


def change_order_status(
    db: Session,
    *,
    order: ServiceOrder,
    new_status: OrderStatus,
    changed_by: User,
    notes: Optional[str] = None,
    time_spent_seconds: Optional[int] = None,
) -> ServiceOrder:
    assert_transition_allowed(order.status, new_status)
    old = order.status
    order.status = new_status
    recompute_total_cost(db, order)
    db.add(order)

    entry = ServiceOrderTimeline(
        service_order_id=order.id,
        old_status=old.value,
        new_status=new_status.value,
        changed_by_id=changed_by.id,
        notes=notes,
        time_spent_seconds=time_spent_seconds,
    )
    db.add(entry)
    return order


def peek_next_order_number(db: Session, company_id) -> int:
    """Valor actual del contador de órdenes (sin reservar número)."""
    n = db.query(Company.next_order_number).filter(Company.id == company_id).scalar()
    return int(n or 1)


def get_cost_line_for_order(
    db: Session, *, company_id, order_id: UUID, line_id: UUID
) -> ServiceOrderCostLine | None:
    return (
        db.query(ServiceOrderCostLine)
        .filter(
            ServiceOrderCostLine.id == line_id,
            ServiceOrderCostLine.service_order_id == order_id,
            ServiceOrderCostLine.company_id == company_id,
        )
        .first()
    )


def add_cost_line(
    db: Session,
    *,
    order: ServiceOrder,
    category: CostLineCategory,
    amount: Decimal,
    description: Optional[str] = None,
    sort_order: int = 0,
) -> ServiceOrderCostLine:
    line = ServiceOrderCostLine(
        company_id=order.company_id,
        service_order_id=order.id,
        category=category,
        description=description,
        amount=amount,
        sort_order=sort_order,
    )
    db.add(line)
    db.flush()
    recompute_total_cost(db, order)
    db.add(order)
    return line


def update_cost_line(
    db: Session,
    *,
    order: ServiceOrder,
    line: ServiceOrderCostLine,
    category: Optional[CostLineCategory] = None,
    amount: Optional[Decimal] = None,
    description: Optional[str] = None,
    sort_order: Optional[int] = None,
) -> ServiceOrderCostLine:
    if category is not None:
        line.category = category
    if amount is not None:
        line.amount = amount
    if description is not None:
        line.description = description
    if sort_order is not None:
        line.sort_order = sort_order
    db.add(line)
    db.flush()
    recompute_total_cost(db, order)
    db.add(order)
    return line


def delete_cost_line(db: Session, *, order: ServiceOrder, line: ServiceOrderCostLine) -> None:
    db.delete(line)
    db.flush()
    recompute_total_cost(db, order)
    db.add(order)
