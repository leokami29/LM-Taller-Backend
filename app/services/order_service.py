from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.dt import utc_now
from app.core.enums import (
    CostLineCategory,
    OrderStatus,
    ServiceOrderKind,
    is_contract_order_kind,
    is_workshop_order_kind,
)
from app.core.exceptions import InvalidOrderTransitionError
from app.core.order_number import format_order_number, parse_order_number
from app.core.tracking_code import allocate_tracking_code
from app.db.models.company import Company
from app.db.models.customer import Customer
from app.db.models.equipment import Equipment
from app.db.models.order_number_sequence import OrderNumberSequence
from app.db.models.rbac import Site
from app.db.models.service_contract import ServiceContract
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


def allocate_order_number(
    db: Session,
    *,
    company_id,
    site: Site,
    order_kind: ServiceOrderKind,
) -> str:
    """Reserva el siguiente número para sede + tipo (transacción con FOR UPDATE)."""
    if not site.code:
        raise ValueError("La sede no tiene código configurado")
    row = (
        db.query(OrderNumberSequence)
        .filter(
            OrderNumberSequence.company_id == company_id,
            OrderNumberSequence.site_id == site.id,
            OrderNumberSequence.order_kind == order_kind,
        )
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        row = OrderNumberSequence(
            company_id=company_id,
            site_id=site.id,
            order_kind=order_kind,
            next_value=1,
        )
        db.add(row)
        db.flush()
        row = (
            db.query(OrderNumberSequence)
            .filter(
                OrderNumberSequence.company_id == company_id,
                OrderNumberSequence.site_id == site.id,
                OrderNumberSequence.order_kind == order_kind,
            )
            .with_for_update()
            .one()
        )
    n = int(row.next_value)
    row.next_value = n + 1
    db.add(row)
    year = utc_now().year
    return format_order_number(site_code=site.code, order_kind=order_kind, year=year, sequence=n)


def peek_next_order_number(
    db: Session,
    *,
    company_id,
    site_id,
    order_kind: ServiceOrderKind,
) -> str:
    """Vista previa del próximo número sin reservarlo."""
    site = (
        db.query(Site)
        .filter(Site.id == site_id, Site.company_id == company_id, Site.is_active.is_(True))
        .first()
    )
    if not site:
        raise ValueError("Sede no válida")
    if not site.code:
        raise ValueError("La sede no tiene código configurado")
    row = (
        db.query(OrderNumberSequence.next_value)
        .filter(
            OrderNumberSequence.company_id == company_id,
            OrderNumberSequence.site_id == site_id,
            OrderNumberSequence.order_kind == order_kind,
        )
        .scalar()
    )
    n = int(row or 1)
    year = utc_now().year
    return format_order_number(site_code=site.code, order_kind=order_kind, year=year, sequence=n)


def _sync_sequences_from_existing_orders(db: Session, *, company_id) -> None:
    """Tras migración: alinea secuencias con órdenes ya creadas en formato nuevo."""
    orders = (
        db.query(ServiceOrder.order_number, ServiceOrder.site_id, ServiceOrder.order_kind)
        .filter(ServiceOrder.company_id == company_id)
        .all()
    )
    max_by_key: dict[tuple, int] = {}
    for order_number, site_id, order_kind in orders:
        if site_id is None:
            continue
        parsed = parse_order_number(order_number)
        if parsed is None:
            continue
        key = (site_id, order_kind)
        max_by_key[key] = max(max_by_key.get(key, 0), parsed.sequence)
    for (site_id, order_kind), max_seq in max_by_key.items():
        row = (
            db.query(OrderNumberSequence)
            .filter(
                OrderNumberSequence.company_id == company_id,
                OrderNumberSequence.site_id == site_id,
                OrderNumberSequence.order_kind == order_kind,
            )
            .one_or_none()
        )
        next_needed = max_seq + 1
        if row is None:
            db.add(
                OrderNumberSequence(
                    company_id=company_id,
                    site_id=site_id,
                    order_kind=order_kind,
                    next_value=next_needed,
                )
            )
        elif row.next_value < next_needed:
            row.next_value = next_needed
            db.add(row)


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
    if not site.code:
        raise ValueError("La sede no tiene código configurado")
    return site


def _assert_service_contract(
    db: Session,
    *,
    company_id,
    contract_id,
    customer_id,
) -> ServiceContract:
    contract = (
        db.query(ServiceContract)
        .filter(
            ServiceContract.id == contract_id,
            ServiceContract.company_id == company_id,
            ServiceContract.is_active.is_(True),
        )
        .first()
    )
    if not contract:
        raise ValueError("Contrato de servicio no encontrado")
    if contract.customer_id != customer_id:
        raise ValueError("El contrato no pertenece al cliente de la orden")
    return contract


def _assert_parent_order(
    db: Session,
    *,
    company_id,
    parent_order_id,
    current_customer_id,
) -> ServiceOrder:
    parent = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.id == parent_order_id, ServiceOrder.company_id == company_id)
        .first()
    )
    if not parent:
        raise ValueError("Orden padre no encontrada")
    if parent.current_customer_id != current_customer_id:
        raise ValueError("La orden padre debe ser del mismo cliente")
    return parent


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
    order_kind: ServiceOrderKind = ServiceOrderKind.WORKSHOP_INTAKE,
    site_id: UUID,
    device_condition_on_entry: Optional[str] = None,
    received_at: Optional[datetime] = None,
    received_by_id: Optional[UUID] = None,
    customer_po_number: Optional[str] = None,
    sales_area: Optional[str] = None,
    assigned_to_id: Optional[UUID] = None,
    estimated_completion: Optional[datetime] = None,
    service_contract_id: Optional[UUID] = None,
    parent_order_id: Optional[UUID] = None,
    portal_submitted_json: Optional[dict] = None,
    accessories_json: Optional[dict] = None,
) -> ServiceOrder:
    if not site_id:
        raise ValueError("La sede es obligatoria para numerar la orden")

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

    site = _assert_company_site(db, company_id=company_id, site_id=site_id)

    if is_contract_order_kind(order_kind):
        if not service_contract_id:
            raise ValueError("Las órdenes por contrato requieren un contrato de servicio")
        _assert_service_contract(
            db,
            company_id=company_id,
            contract_id=service_contract_id,
            customer_id=current_customer_id,
        )
    elif service_contract_id:
        raise ValueError("Solo las órdenes por contrato pueden asociar un contrato")

    if parent_order_id:
        _assert_parent_order(
            db,
            company_id=company_id,
            parent_order_id=parent_order_id,
            current_customer_id=current_customer_id,
        )

    reception_user_id = received_by_id or created_by_id
    if reception_user_id:
        _assert_company_user(db, company_id=company_id, user_id=reception_user_id)

    if assigned_to_id:
        _assert_company_user(db, company_id=company_id, user_id=assigned_to_id)

    intake_at: datetime | None = None
    if is_workshop_order_kind(order_kind):
        intake_at = received_at or utc_now()
        if estimated_completion and estimated_completion < intake_at:
            raise ValueError("La fecha prometida no puede ser anterior al ingreso")
    elif estimated_completion and received_at and estimated_completion < received_at:
        raise ValueError("La fecha programada no puede ser anterior al registro")

    order_number = allocate_order_number(
        db, company_id=company_id, site=site, order_kind=order_kind
    )
    tracking_code = allocate_tracking_code(db, company_id=company_id)

    order = ServiceOrder(
        company_id=company_id,
        order_number=order_number,
        tracking_code=tracking_code,
        order_kind=order_kind,
        equipment_id=equipment_id,
        current_customer_id=current_customer_id,
        original_owner_id=original_owner_id,
        status=OrderStatus.RECEIVED,
        priority=priority,
        problem_description=problem_description,
        device_condition_on_entry=device_condition_on_entry if is_workshop_order_kind(order_kind) else None,
        cost_parts=Decimal("0"),
        cost_labor=Decimal("0"),
        total_cost=Decimal("0"),
        created_by_id=created_by_id,
        site_id=site_id,
        received_at=intake_at,
        received_by_id=reception_user_id if is_workshop_order_kind(order_kind) else None,
        customer_po_number=customer_po_number,
        sales_area=sales_area,
        assigned_to_id=assigned_to_id,
        estimated_completion=estimated_completion,
        service_contract_id=service_contract_id,
        parent_order_id=parent_order_id,
        portal_submitted_json=portal_submitted_json,
        accessories_json=accessories_json,
    )
    db.add(order)
    db.flush()

    entry = ServiceOrderTimeline(
        service_order_id=order.id,
        old_status=None,
        new_status=OrderStatus.RECEIVED.value,
        changed_by_id=created_by_id,
        notes="Orden creada",
    )
    db.add(entry)
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
    description: Optional[str],
    sort_order: int,
) -> ServiceOrderCostLine:
    line = ServiceOrderCostLine(
        company_id=order.company_id,
        service_order_id=order.id,
        category=category,
        amount=amount,
        description=description,
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
    line: ServiceOrderCostLine,
    order: ServiceOrder,
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
    recompute_total_cost(db, order)
    db.add(order)
    return line


def delete_cost_line(db: Session, *, line: ServiceOrderCostLine, order: ServiceOrder) -> None:
    db.delete(line)
    db.flush()
    recompute_total_cost(db, order)
    db.add(order)
