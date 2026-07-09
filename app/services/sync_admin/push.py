from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID

from app.core.enums import SubscriptionStatus, UserRole
from app.core.subscription_lifecycle import validate_subscription_period_status
from app.db.models.company import Company
from app.db.models.customer import Customer
from app.db.models.equipment import Equipment
from app.db.models.inventory import InventoryItem
from app.db.models.rbac import Site, UserSiteRole
from app.db.models.service_contract import ServiceContract
from app.db.models.service_order import ServiceOrder
from app.db.models.user import User
from app.schemas.sync_admin import AdminMutation, AdminPushItemResult, SyncContext
from app.services.permission_service import PermissionService
from app.services.tenant_config_events import bump_company_config_revision


def as_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def applied(mutation: AdminMutation) -> AdminPushItemResult:
    return AdminPushItemResult(
        mutation_id=mutation.mutation_id,
        entity=mutation.entity,
        entity_id=mutation.entity_id,
        status="applied",
    )


def rejected(mutation: AdminMutation, detail: str) -> AdminPushItemResult:
    return AdminPushItemResult(
        mutation_id=mutation.mutation_id,
        entity=mutation.entity,
        entity_id=mutation.entity_id,
        status="rejected",
        detail=detail,
    )


def reject_if_stale(existing: Any, mutation: AdminMutation) -> AdminPushItemResult | None:
    current = getattr(existing, "updated_at", None)
    if current is not None and as_utc_aware(current) > as_utc_aware(mutation.updated_at):
        return AdminPushItemResult(
            mutation_id=mutation.mutation_id,
            entity=mutation.entity,
            entity_id=mutation.entity_id,
            status="conflict",
            detail="El servidor tiene una version mas reciente",
        )
    return None


def load_company_or_reject(
    ctx: SyncContext, mutation: AdminMutation
) -> tuple[Company | None, AdminPushItemResult | None]:
    company = ctx.db.query(Company).filter(Company.id == ctx.company_id).first()
    if not company:
        return None, rejected(mutation, "Empresa no encontrada")
    conflict = reject_if_stale(company, mutation)
    if conflict:
        return None, conflict
    return company, None


def apply_company(ctx: SyncContext, mutation: AdminMutation) -> AdminPushItemResult:
    company, rejection = load_company_or_reject(ctx, mutation)
    if rejection:
        return rejection
    if mutation.op not in ("update",):
        return rejected(mutation, "Operacion no soportada para company")
    if "subscription_status" in mutation.payload or "current_period_end" in mutation.payload:
        try:
            status_value = SubscriptionStatus(mutation.payload.get("subscription_status", company.subscription_status))
            period_end = mutation.payload.get("current_period_end")
            if isinstance(period_end, str):
                period_end = datetime.fromisoformat(period_end)
            validate_subscription_period_status(status_value, period_end)
        except ValueError as exc:
            return rejected(mutation, str(exc))
        return rejected(mutation, "La suscripcion se administra desde plataforma")
    allowed = {"name", "address", "phone", "email", "country", "currency"}
    for key, value in mutation.payload.items():
        if key in allowed:
            setattr(company, key, value)
    company.updated_at = mutation.updated_at
    bump_company_config_revision(company)
    ctx.db.add(company)
    return applied(mutation)


def apply_session_policy(ctx: SyncContext, mutation: AdminMutation) -> AdminPushItemResult:
    company, rejection = load_company_or_reject(ctx, mutation)
    if rejection:
        return rejection
    settings_json = dict(company.settings_json or {})
    settings_json["session_policies"] = mutation.payload.get("session_policies", {})
    company.settings_json = settings_json
    company.updated_at = mutation.updated_at
    bump_company_config_revision(company)
    ctx.db.add(company)
    return applied(mutation)


def apply_site(ctx: SyncContext, mutation: AdminMutation) -> AdminPushItemResult:
    site = ctx.db.query(Site).filter(Site.id == mutation.entity_id, Site.company_id == ctx.company_id).first()
    if mutation.op == "create":
        if site:
            return applied(mutation)
        from app.services.site_code_service import derive_site_code, validate_site_code

        site_name = str(mutation.payload.get("name") or "Nueva sede")
        existing = {row[0] for row in ctx.db.query(Site.code).filter(Site.company_id == ctx.company_id).all()}
        raw_code = mutation.payload.get("code")
        code = validate_site_code(str(raw_code)) if raw_code else derive_site_code(site_name, existing)
        site = Site(
            id=mutation.entity_id,
            company_id=ctx.company_id,
            code=code,
            name=site_name,
            location=mutation.payload.get("location"),
            is_active=bool(mutation.payload.get("is_active", True)),
            updated_at=mutation.updated_at,
        )
        ctx.db.add(site)
        return applied(mutation)
    if not site:
        return rejected(mutation, "Sede no encontrada")
    conflict = reject_if_stale(site, mutation)
    if conflict:
        return conflict
    if mutation.op == "delete":
        site.is_active = False
    elif mutation.op == "update":
        for key in ("name", "location", "is_active"):
            if key in mutation.payload:
                setattr(site, key, mutation.payload[key])
    else:
        return rejected(mutation, "Operacion no soportada para site")
    site.updated_at = mutation.updated_at
    ctx.db.add(site)
    return applied(mutation)


def apply_user(ctx: SyncContext, mutation: AdminMutation) -> AdminPushItemResult:
    user = ctx.db.query(User).filter(User.id == mutation.entity_id, User.company_id == ctx.company_id).first()
    if mutation.op == "create":
        if user:
            return applied(mutation)
        ok, reason = PermissionService(ctx.db).can_add_user(ctx.company_id)
        if not ok:
            return rejected(mutation, reason)
        password_hash = mutation.payload.get("hashed_password")
        if not password_hash:
            return rejected(mutation, "hashed_password es obligatorio para crear usuario offline")
        user = User(
            id=mutation.entity_id,
            company_id=ctx.company_id,
            email=str(mutation.payload.get("email")),
            full_name=str(mutation.payload.get("full_name") or ""),
            hashed_password=str(password_hash),
            role=UserRole(mutation.payload.get("role", UserRole.RECEPTION.value)),
            phone=mutation.payload.get("phone"),
            is_active=bool(mutation.payload.get("is_active", True)),
            created_by_id=ctx.user.id,
            updated_at=mutation.updated_at,
        )
        ctx.db.add(user)
        return applied(mutation)
    if not user:
        return rejected(mutation, "Usuario no encontrado")
    conflict = reject_if_stale(user, mutation)
    if conflict:
        return conflict
    if mutation.op == "deactivate":
        user.is_active = False
    elif mutation.op == "reset_password":
        if not mutation.payload.get("hashed_password"):
            return rejected(mutation, "hashed_password es obligatorio")
        user.hashed_password = str(mutation.payload["hashed_password"])
    elif mutation.op == "update":
        for key in ("full_name", "phone", "is_active"):
            if key in mutation.payload:
                setattr(user, key, mutation.payload[key])
    else:
        return rejected(mutation, "Operacion no soportada para user")
    user.updated_at = mutation.updated_at
    ctx.db.add(user)
    return applied(mutation)


def apply_user_site_role(ctx: SyncContext, mutation: AdminMutation) -> AdminPushItemResult:
    role = (
        ctx.db.query(UserSiteRole)
        .filter(UserSiteRole.id == mutation.entity_id, UserSiteRole.company_id == ctx.company_id)
        .first()
    )
    if mutation.op == "create":
        if role:
            return applied(mutation)
        role = UserSiteRole(
            id=mutation.entity_id,
            user_id=UUID(str(mutation.payload["user_id"])),
            company_id=ctx.company_id,
            site_id=UUID(str(mutation.payload["site_id"])) if mutation.payload.get("site_id") else None,
            role=UserRole(mutation.payload["role"]),
            is_active=bool(mutation.payload.get("is_active", True)),
            updated_at=mutation.updated_at,
        )
        ctx.db.add(role)
        return applied(mutation)
    if not role:
        return rejected(mutation, "Rol de sede no encontrado")
    conflict = reject_if_stale(role, mutation)
    if conflict:
        return conflict
    if mutation.op == "delete":
        role.is_active = False
    elif mutation.op == "update":
        if "role" in mutation.payload:
            role.role = UserRole(mutation.payload["role"])
        if "site_id" in mutation.payload:
            role.site_id = UUID(str(mutation.payload["site_id"])) if mutation.payload["site_id"] else None
        if "is_active" in mutation.payload:
            role.is_active = bool(mutation.payload["is_active"])
    else:
        return rejected(mutation, "Operacion no soportada para user_site_role")
    role.updated_at = mutation.updated_at
    ctx.db.add(role)
    return applied(mutation)


def apply_customer(ctx: SyncContext, mutation: AdminMutation) -> AdminPushItemResult:
    from app.core.enums import IdentificationType

    customer = (
        ctx.db.query(Customer)
        .filter(Customer.id == mutation.entity_id, Customer.company_id == ctx.company_id)
        .first()
    )
    if mutation.op == "create":
        if customer:
            return applied(mutation)
        customer = Customer(
            id=mutation.entity_id,
            company_id=ctx.company_id,
            first_name=str(mutation.payload.get("first_name", "")),
            last_name=str(mutation.payload.get("last_name", "")),
            email=mutation.payload.get("email"),
            phone=mutation.payload.get("phone"),
            address=mutation.payload.get("address"),
            identification_type=(
                IdentificationType(mutation.payload["identification_type"])
                if mutation.payload.get("identification_type")
                else None
            ),
            identification_number=mutation.payload.get("identification_number"),
            rut=mutation.payload.get("rut"),
            city=mutation.payload.get("city"),
            country=mutation.payload.get("country"),
            notes=mutation.payload.get("notes"),
            updated_at=mutation.updated_at,
        )
        ctx.db.add(customer)
        return applied(mutation)
    if not customer:
        return rejected(mutation, "Cliente no encontrado")
    conflict = reject_if_stale(customer, mutation)
    if conflict:
        return conflict
    if mutation.op == "delete":
        customer.is_active = False if hasattr(customer, "is_active") else None
        ctx.db.delete(customer)
    elif mutation.op == "update":
        for key in (
            "first_name",
            "last_name",
            "email",
            "phone",
            "address",
            "identification_number",
            "rut",
            "city",
            "country",
            "notes",
        ):
            if key in mutation.payload:
                setattr(customer, key, mutation.payload[key])
    else:
        return rejected(mutation, "Operación no soportada para customer")
    customer.updated_at = mutation.updated_at
    ctx.db.add(customer)
    return applied(mutation)


def apply_equipment(ctx: SyncContext, mutation: AdminMutation) -> AdminPushItemResult:
    equipment = (
        ctx.db.query(Equipment)
        .filter(Equipment.id == mutation.entity_id, Equipment.company_id == ctx.company_id)
        .first()
    )
    if mutation.op == "create":
        if equipment:
            return applied(mutation)
        equipment = Equipment(
            id=mutation.entity_id,
            company_id=ctx.company_id,
            serial_number=str(mutation.payload.get("serial_number", "")),
            equipment_type=mutation.payload.get("equipment_type"),
            category=mutation.payload.get("category"),
            brand=mutation.payload.get("brand"),
            model=mutation.payload.get("model"),
            original_owner_id=(
                UUID(str(mutation.payload["original_owner_id"])) if mutation.payload.get("original_owner_id") else None
            ),
            updated_at=mutation.updated_at,
        )
        ctx.db.add(equipment)
        return applied(mutation)
    if not equipment:
        return rejected(mutation, "Equipo no encontrado")
    conflict = reject_if_stale(equipment, mutation)
    if conflict:
        return conflict
    if mutation.op in ("update", "status_change"):
        allowed = (
            "equipment_type",
            "category",
            "subcategory",
            "brand",
            "model",
            "manufacturer",
            "imei",
            "color",
            "barcode",
            "status",
            "location",
            "additional_notes",
            "custom_fields",
        )
        for key in allowed:
            if key in mutation.payload:
                setattr(equipment, key, mutation.payload[key])
    elif mutation.op == "delete":
        ctx.db.delete(equipment)
    else:
        return rejected(mutation, "Operación no soportada para equipment")
    equipment.updated_at = mutation.updated_at
    ctx.db.add(equipment)
    return applied(mutation)


def apply_service_order(ctx: SyncContext, mutation: AdminMutation) -> AdminPushItemResult:
    from app.core.enums import OrderPriority, OrderStatus

    order = (
        ctx.db.query(ServiceOrder)
        .filter(ServiceOrder.id == mutation.entity_id, ServiceOrder.company_id == ctx.company_id)
        .first()
    )
    if mutation.op == "create":
        if order:
            return applied(mutation)
        try:
            order = ServiceOrder(
                id=mutation.entity_id,
                company_id=ctx.company_id,
                order_number=str(mutation.payload.get("order_number", "")),
                order_kind=mutation.payload.get("order_kind", "workshop_intake"),
                equipment_id=(
                    UUID(str(mutation.payload["equipment_id"]))
                    if mutation.payload.get("equipment_id")
                    else None
                ),
                current_customer_id=(
                    UUID(str(mutation.payload["current_customer_id"]))
                    if mutation.payload.get("current_customer_id")
                    else None
                ),
                status=OrderStatus(mutation.payload.get("status", "received")),
                priority=OrderPriority(mutation.payload.get("priority", "medium")),
                problem_description=str(mutation.payload.get("problem_description", "")),
                assigned_to_id=(
                    UUID(str(mutation.payload["assigned_to_id"])) if mutation.payload.get("assigned_to_id") else None
                ),
                site_id=UUID(str(mutation.payload["site_id"])) if mutation.payload.get("site_id") else None,
                updated_at=mutation.updated_at,
            )
        except (KeyError, ValueError) as exc:
            return rejected(mutation, f"Payload inválido para service_order: {exc}")
        ctx.db.add(order)
        return applied(mutation)
    if not order:
        return rejected(mutation, "Orden no encontrada")
    conflict = reject_if_stale(order, mutation)
    if conflict:
        return conflict
    if mutation.op in ("update", "status_change"):
        allowed = (
            "status",
            "priority",
            "assigned_to_id",
            "diagnosis_notes",
            "estimated_completion",
            "actual_completion",
            "cost_parts",
            "cost_labor",
            "total_cost",
            "device_condition_on_entry",
            "site_id",
        )
        for key in allowed:
            if key in mutation.payload:
                val = mutation.payload[key]
                if key in ("assigned_to_id", "site_id") and val:
                    val = UUID(str(val))
                elif key == "status":
                    val = OrderStatus(val)
                elif key == "priority":
                    val = OrderPriority(val)
                setattr(order, key, val)
    elif mutation.op == "delete":
        ctx.db.delete(order)
    else:
        return rejected(mutation, "Operación no soportada para service_order")
    order.updated_at = mutation.updated_at
    ctx.db.add(order)
    return applied(mutation)


def apply_inventory_item(ctx: SyncContext, mutation: AdminMutation) -> AdminPushItemResult:
    item = (
        ctx.db.query(InventoryItem)
        .filter(InventoryItem.id == mutation.entity_id, InventoryItem.company_id == ctx.company_id)
        .first()
    )
    if mutation.op == "create":
        if item:
            return applied(mutation)
        item = InventoryItem(
            id=mutation.entity_id,
            company_id=ctx.company_id,
            sku=str(mutation.payload.get("sku", "")),
            name=str(mutation.payload.get("name", "")),
            item_type=mutation.payload.get("item_type"),
            description=mutation.payload.get("description"),
            category=mutation.payload.get("category"),
            quantity_stock=mutation.payload.get("quantity_stock", 0),
            quantity_minimum=mutation.payload.get("quantity_minimum", 0),
            unit_cost=mutation.payload.get("unit_cost"),
            unit_price=mutation.payload.get("unit_price"),
            updated_at=mutation.updated_at,
        )
        ctx.db.add(item)
        return applied(mutation)
    if not item:
        return rejected(mutation, "Ítem de inventario no encontrado")
    conflict = reject_if_stale(item, mutation)
    if conflict:
        return conflict
    if mutation.op in ("update", "stock_change"):
        allowed = ("name", "description", "category", "quantity_stock", "quantity_minimum", "unit_cost", "unit_price")
        for key in allowed:
            if key in mutation.payload:
                setattr(item, key, mutation.payload[key])
    elif mutation.op == "delete":
        ctx.db.delete(item)
    else:
        return rejected(mutation, "Operación no soportada para inventory_item")
    item.updated_at = mutation.updated_at
    ctx.db.add(item)
    return applied(mutation)


def apply_service_contract(ctx: SyncContext, mutation: AdminMutation) -> AdminPushItemResult:
    contract = (
        ctx.db.query(ServiceContract)
        .filter(ServiceContract.id == mutation.entity_id, ServiceContract.company_id == ctx.company_id)
        .first()
    )
    if mutation.op == "create":
        if contract:
            return applied(mutation)
        from app.core.enums import ContractKind

        contract = ServiceContract(
            id=mutation.entity_id,
            company_id=ctx.company_id,
            customer_id=UUID(str(mutation.payload["customer_id"])),
            contract_number=str(mutation.payload.get("contract_number", "")),
            name=str(mutation.payload.get("name", "")),
            contract_kind=ContractKind(mutation.payload.get("contract_kind", "custom")),
            updated_at=mutation.updated_at,
        )
        ctx.db.add(contract)
        return applied(mutation)
    if not contract:
        return rejected(mutation, "Contrato no encontrado")
    conflict = reject_if_stale(contract, mutation)
    if conflict:
        return conflict
    if mutation.op == "update":
        for key in ("name", "is_active", "notes"):
            if key in mutation.payload:
                setattr(contract, key, mutation.payload[key])
    elif mutation.op == "delete":
        contract.is_active = False
    else:
        return rejected(mutation, "Operación no soportada para service_contract")
    contract.updated_at = mutation.updated_at
    ctx.db.add(contract)
    return applied(mutation)


_ENTITY_HANDLERS: dict[str, Callable[[SyncContext, AdminMutation], AdminPushItemResult]] = {
    "company": apply_company,
    "session_policy": apply_session_policy,
    "site": apply_site,
    "user": apply_user,
    "user_site_role": apply_user_site_role,
    "customer": apply_customer,
    "equipment": apply_equipment,
    "service_order": apply_service_order,
    "inventory_item": apply_inventory_item,
    "service_contract": apply_service_contract,
}


def apply_mutation(ctx: SyncContext, mutation: AdminMutation) -> AdminPushItemResult:
    if mutation.entity == "role_change_request":
        return rejected(mutation, "Use la API REST para gestionar solicitudes de cambio de rol")
    if mutation.entity == "temporary_permission":
        return rejected(mutation, "Use la API REST para gestionar permisos temporales")
    if mutation.entity == "audit_log":
        return rejected(mutation, "Los registros de auditoria son solo lectura")
    handler = _ENTITY_HANDLERS.get(mutation.entity)
    if handler is None:
        return rejected(mutation, "Entidad no soportada")
    return handler(ctx, mutation)
