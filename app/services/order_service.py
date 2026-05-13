from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.enums import CostLineCategory, OrderStatus
from app.core.exceptions import InvalidOrderTransitionError
from app.db.models.company import Company
from app.db.models.customer import Customer
from app.db.models.equipment import Equipment
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

    order_number = allocate_order_number(db, company_id)
    desc = problem_description
    if device_condition_on_entry:
        desc = f"[Condición al ingreso: {device_condition_on_entry}]\n{problem_description}"

    order = ServiceOrder(
        company_id=company_id,
        order_number=order_number,
        equipment_id=equipment_id,
        current_customer_id=current_customer_id,
        original_owner_id=original_owner_id,
        status=OrderStatus.RECEIVED,
        priority=priority,
        problem_description=desc,
        cost_parts=Decimal("0"),
        cost_labor=Decimal("0"),
        total_cost=Decimal("0"),
        created_by_id=created_by_id,
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
