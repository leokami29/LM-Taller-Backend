from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.core.contract_template import normalize_template, validate_allowed_order_kinds
from app.core.dt import utc_now
from app.core.enums import ServiceOrderKind
from app.db.models.customer import Customer
from app.db.models.rbac import Site
from app.db.models.service_contract import ServiceContract
from app.db.models.service_order import ServiceOrder
from app.utils.helpers import apply_allowed_updates


def _assert_customer(db: Session, *, company_id, customer_id) -> Customer:
    row = (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.company_id == company_id)
        .first()
    )
    if not row:
        raise ValueError("Cliente no encontrado")
    return row


def _assert_site(db: Session, *, company_id, site_id) -> Site:
    row = (
        db.query(Site)
        .filter(Site.id == site_id, Site.company_id == company_id, Site.is_active.is_(True))
        .first()
    )
    if not row:
        raise ValueError("Sede no válida")
    if not row.code:
        raise ValueError("La sede no tiene código configurado")
    return row


def contract_is_active(contract: ServiceContract, *, on_date: date | None = None) -> bool:
    if not contract.is_active:
        return False
    today = on_date or utc_now().date()
    if contract.valid_from and today < contract.valid_from:
        return False
    if contract.valid_to and today > contract.valid_to:
        return False
    return True


def count_contract_orders_this_month(db: Session, *, company_id, contract_id) -> int:
    now = utc_now()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return (
        db.query(ServiceOrder.id)
        .filter(
            ServiceOrder.company_id == company_id,
            ServiceOrder.service_contract_id == contract_id,
            ServiceOrder.created_at >= start,
        )
        .count()
    )


def prepare_contract_fields(
    *,
    allowed_order_kinds: list[ServiceOrderKind],
    template_json: dict | None,
) -> tuple[list[str], dict]:
    kinds = validate_allowed_order_kinds([k.value if isinstance(k, ServiceOrderKind) else str(k) for k in allowed_order_kinds])
    template = normalize_template(template_json)
    return kinds, template


def create_contract(
    db: Session,
    *,
    company_id,
    customer_id,
    contract_number: str,
    name: str,
    contract_kind,
    default_site_id,
    allowed_order_kinds: list[ServiceOrderKind],
    template_json: dict | None,
    max_orders_per_month: Optional[int],
    valid_from: Optional[date],
    valid_to: Optional[date],
    is_active: bool = True,
) -> ServiceContract:
    _assert_customer(db, company_id=company_id, customer_id=customer_id)
    _assert_site(db, company_id=company_id, site_id=default_site_id)
    if valid_from and valid_to and valid_to < valid_from:
        raise ValueError("valid_to no puede ser anterior a valid_from")
    kinds, template = prepare_contract_fields(
        allowed_order_kinds=allowed_order_kinds,
        template_json=template_json,
    )
    existing = (
        db.query(ServiceContract.id)
        .filter(
            ServiceContract.company_id == company_id,
            ServiceContract.contract_number == contract_number,
        )
        .first()
    )
    if existing:
        raise ValueError("Ya existe un contrato con ese número")
    row = ServiceContract(
        company_id=company_id,
        customer_id=customer_id,
        contract_number=contract_number,
        name=name,
        contract_kind=contract_kind,
        default_site_id=default_site_id,
        allowed_order_kinds=kinds,
        template_json=template,
        max_orders_per_month=max_orders_per_month,
        valid_from=valid_from,
        valid_to=valid_to,
        is_active=is_active,
    )
    db.add(row)
    db.flush()
    return row


def get_contract_for_company(
    db: Session, *, company_id, contract_id
) -> ServiceContract | None:
    return (
        db.query(ServiceContract)
        .filter(ServiceContract.id == contract_id, ServiceContract.company_id == company_id)
        .first()
    )


def delete_contract(db: Session, *, contract: ServiceContract) -> None:
    contract.is_active = False
    db.add(contract)


def update_contract(
    db: Session,
    *,
    contract: ServiceContract,
    data: dict,
) -> ServiceContract:
    if "customer_id" in data:
        _assert_customer(db, company_id=contract.company_id, customer_id=data["customer_id"])
    if "default_site_id" in data and data["default_site_id"]:
        _assert_site(db, company_id=contract.company_id, site_id=data["default_site_id"])
    if "allowed_order_kinds" in data and data["allowed_order_kinds"] is not None:
        kinds, _ = prepare_contract_fields(
            allowed_order_kinds=data["allowed_order_kinds"],
            template_json=data.get("template_json") or contract.template_json,
        )
        contract.allowed_order_kinds = kinds
        data.pop("allowed_order_kinds", None)
    if "template_json" in data and data["template_json"] is not None:
        contract.template_json = normalize_template(data["template_json"])
        data.pop("template_json", None)
    vf, vt = data.get("valid_from", contract.valid_from), data.get("valid_to", contract.valid_to)
    if vf and vt and vt < vf:
        raise ValueError("valid_to no puede ser anterior a valid_from")
    apply_allowed_updates(contract, data, (
        "contract_number", "name", "contract_kind", "max_orders_per_month",
        "valid_from", "valid_to", "is_active",
    ))
    db.add(contract)
    return contract
