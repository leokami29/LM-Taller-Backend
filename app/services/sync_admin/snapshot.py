from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from app.config import settings
from app.core.dt import utc_now
from app.core.subscription_lifecycle import subscription_is_usable
from app.db.catalog.models import TenantRouting
from app.db.models.audit_log import AuditLog
from app.db.models.company import Company
from app.db.models.customer import Customer
from app.db.models.equipment import Equipment, EquipmentAttribute
from app.db.models.inventory import InventoryItem, InventoryMovement
from app.db.models.inventory_category import InventoryCategory
from app.db.models.rbac import RoleChangeRequest, Site, TemporaryPermission, UserSiteRole
from app.db.models.service_contract import ServiceContract
from app.db.models.service_order import ServiceOrder
from app.db.models.service_order_image import ServiceOrderImage
from app.db.models.user import User
from app.db.session import catalog_session_scope
from app.schemas.sync_admin import AdminSyncSnapshot, SyncContext
from app.services.installation_service import record_installation_sync
from app.services.license_manifest_service import build_license_manifest
from app.services.permission_service import PermissionService


def max_cursor(*groups: list[dict[str, Any]]) -> str:
    values = [
        item.get("updated_at")
        for group in groups
        for item in group
        if item.get("updated_at") is not None
    ]
    if not values:
        return utc_now().isoformat()
    return max(str(v) for v in values)


_USER_SECRET_KEYS = frozenset({"hashed_password", "password", "password_hash"})
_EMAIL_SECRET_KEYS = frozenset({"smtp_password", "password"})


def row(model: Any) -> dict[str, Any]:
    return jsonable_encoder(model)


def sanitize_user_row(data: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(data)
    for key in _USER_SECRET_KEYS:
        cleaned.pop(key, None)
    return cleaned


def sanitize_company_row(data: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(data)
    settings = dict(cleaned.get("settings_json") or {})
    email = dict(settings.get("email_settings") or {})
    for key in _EMAIL_SECRET_KEYS:
        email.pop(key, None)
    if "email_settings" in settings or email:
        settings["email_settings"] = email
    cleaned["settings_json"] = settings
    return cleaned


def build_snapshot(ctx: SyncContext) -> AdminSyncSnapshot:
    company = ctx.db.query(Company).filter(Company.id == ctx.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    sites = ctx.db.query(Site).filter(Site.company_id == ctx.company_id).order_by(Site.name).all()
    users = ctx.db.query(User).filter(User.company_id == ctx.company_id).order_by(User.created_at.desc()).all()
    roles = (
        ctx.db.query(UserSiteRole)
        .filter(UserSiteRole.company_id == ctx.company_id)
        .order_by(UserSiteRole.created_at.desc())
        .all()
    )
    customers = (
        ctx.db.query(Customer).filter(Customer.company_id == ctx.company_id).order_by(Customer.created_at.desc()).all()
    )
    equipment = (
        ctx.db.query(Equipment)
        .filter(Equipment.company_id == ctx.company_id)
        .order_by(Equipment.created_at.desc())
        .all()
    )
    orders = (
        ctx.db.query(ServiceOrder)
        .filter(ServiceOrder.company_id == ctx.company_id)
        .order_by(ServiceOrder.created_at.desc())
        .all()
    )
    order_ids = [o.id for o in orders]
    order_images = (
        ctx.db.query(ServiceOrderImage)
        .filter(ServiceOrderImage.service_order_id.in_(order_ids))
        .order_by(ServiceOrderImage.sort_order, ServiceOrderImage.created_at)
        .all()
    ) if order_ids else []
    inv_categories = (
        ctx.db.query(InventoryCategory)
        .filter(InventoryCategory.company_id == ctx.company_id)
        .order_by(InventoryCategory.name)
        .all()
    )
    inv_items = (
        ctx.db.query(InventoryItem)
        .filter(InventoryItem.company_id == ctx.company_id)
        .order_by(InventoryItem.created_at.desc())
        .all()
    )
    inv_item_ids = [i.id for i in inv_items]
    inv_movements = (
        ctx.db.query(InventoryMovement)
        .filter(InventoryMovement.inventory_item_id.in_(inv_item_ids))
        .order_by(InventoryMovement.moved_at.desc())
        .all()
    ) if inv_item_ids else []
    contracts = (
        ctx.db.query(ServiceContract)
        .filter(ServiceContract.company_id == ctx.company_id)
        .order_by(ServiceContract.created_at.desc())
        .all()
    )
    role_change_reqs = (
        ctx.db.query(RoleChangeRequest)
        .filter(RoleChangeRequest.company_id == ctx.company_id)
        .order_by(RoleChangeRequest.created_at.desc())
        .all()
    )
    temp_perms = (
        ctx.db.query(TemporaryPermission)
        .filter(TemporaryPermission.company_id == ctx.company_id)
        .order_by(TemporaryPermission.created_at.desc())
        .all()
    )
    audit_logs = (
        ctx.db.query(AuditLog)
        .filter(AuditLog.company_id == ctx.company_id)
        .order_by(AuditLog.created_at.desc())
        .all()
    )
    equipment_ids = [e.id for e in equipment]
    eq_attrs = (
        ctx.db.query(EquipmentAttribute)
        .filter(EquipmentAttribute.equipment_id.in_(equipment_ids))
        .order_by(EquipmentAttribute.key)
        .all()
    ) if equipment_ids else []
    svc = PermissionService(ctx.db)
    ent = svc.get_entitlements(ctx.company_id)
    period_end = svc.get_subscription_period_end(ctx.company_id)
    site_rows = [row(s) for s in sites]
    user_rows = [sanitize_user_row(row(u)) for u in users]
    role_rows = [row(r) for r in roles]
    company_row = sanitize_company_row(row(company))
    customer_rows = [row(c) for c in customers]
    equipment_rows = [row(e) for e in equipment]
    order_rows = [row(o) for o in orders]
    order_image_rows = [row(i) for i in order_images]
    category_rows = [row(c) for c in inv_categories]
    item_rows = [row(i) for i in inv_items]
    movement_rows = [row(m) for m in inv_movements]
    contract_rows = [row(c) for c in contracts]
    role_change_req_rows = [row(r) for r in role_change_reqs]
    temp_perm_rows = [row(t) for t in temp_perms]
    audit_log_rows = [row(a) for a in audit_logs]
    eq_attr_rows = [row(a) for a in eq_attrs]
    return AdminSyncSnapshot(
        company_id=ctx.company_id,
        cursor=max_cursor(
            [company_row],
            site_rows,
            user_rows,
            role_rows,
            customer_rows,
            equipment_rows,
            order_rows,
            category_rows,
            item_rows,
            movement_rows,
            contract_rows,
            order_image_rows,
            role_change_req_rows,
            temp_perm_rows,
        ),
        company=company_row,
        sites=site_rows,
        users=user_rows,
        user_site_roles=role_rows,
        entitlements={
            "plan": ent.plan.value,
            "status": ent.status.value,
            "subscription_usable": subscription_is_usable(ent.status, period_end),
            "current_period_end": period_end,
            "billing_email": svc.get_billing_email(ctx.company_id),
            "limits": {
                "max_users": ent.max_users,
                "max_orders_month": ent.max_orders_month,
                "storage_mb": ent.storage_mb,
            },
        },
        customers=customer_rows,
        equipment=equipment_rows,
        equipment_attributes=eq_attr_rows,
        service_orders=order_rows,
        service_order_images=order_image_rows,
        inventory_categories=category_rows,
        inventory_items=item_rows,
        inventory_movements=movement_rows,
        service_contracts=contract_rows,
        role_change_requests=role_change_req_rows,
        temporary_permissions=temp_perm_rows,
        audit_logs=audit_log_rows,
    )


def filter_snapshot_since(snapshot: AdminSyncSnapshot, since: datetime) -> AdminSyncSnapshot:
    since_iso = since.isoformat()
    snapshot.sites = [r for r in snapshot.sites if r.get("updated_at") and str(r["updated_at"]) > since_iso]
    snapshot.users = [r for r in snapshot.users if r.get("updated_at") and str(r["updated_at"]) > since_iso]
    snapshot.user_site_roles = [
        r for r in snapshot.user_site_roles if r.get("updated_at") and str(r["updated_at"]) > since_iso
    ]
    snapshot.customers = [r for r in snapshot.customers if r.get("updated_at") and str(r["updated_at"]) > since_iso]
    snapshot.equipment = [r for r in snapshot.equipment if r.get("updated_at") and str(r["updated_at"]) > since_iso]
    snapshot.service_orders = [
        r for r in snapshot.service_orders if r.get("updated_at") and str(r["updated_at"]) > since_iso
    ]
    snapshot.service_order_images = [
        r for r in snapshot.service_order_images if r.get("created_at") and str(r["created_at"]) > since_iso
    ]
    snapshot.inventory_categories = [
        r for r in snapshot.inventory_categories if r.get("updated_at") and str(r["updated_at"]) > since_iso
    ]
    snapshot.inventory_items = [
        r for r in snapshot.inventory_items if r.get("updated_at") and str(r["updated_at"]) > since_iso
    ]
    snapshot.inventory_movements = [
        r for r in snapshot.inventory_movements if r.get("moved_at") and str(r["moved_at"]) > since_iso
    ]
    snapshot.service_contracts = [
        r for r in snapshot.service_contracts if r.get("updated_at") and str(r["updated_at"]) > since_iso
    ]
    snapshot.role_change_requests = [
        r for r in snapshot.role_change_requests if r.get("updated_at") and str(r["updated_at"]) > since_iso
    ]
    snapshot.temporary_permissions = [
        r for r in snapshot.temporary_permissions if r.get("updated_at") and str(r["updated_at"]) > since_iso
    ]
    snapshot.audit_logs = [
        r for r in snapshot.audit_logs if r.get("created_at") and str(r["created_at"]) > since_iso
    ]
    eq_ids_in_snapshot = {str(eq.get("id")) for eq in snapshot.equipment}
    snapshot.equipment_attributes = [
        attr for attr in snapshot.equipment_attributes if str(attr.get("equipment_id")) in eq_ids_in_snapshot
    ]
    order_ids_in_snapshot = {str(o.get("id")) for o in snapshot.service_orders}
    snapshot.service_order_images = [
        img for img in snapshot.service_order_images if str(img.get("service_order_id")) in order_ids_in_snapshot
    ]
    if snapshot.company.get("updated_at") and str(snapshot.company["updated_at"]) <= since_iso:
        snapshot.company = {}
    snapshot.cursor = max_cursor(
        [snapshot.company] if snapshot.company else [],
        snapshot.sites,
        snapshot.users,
        snapshot.user_site_roles,
        snapshot.customers,
        snapshot.equipment,
        snapshot.service_orders,
        snapshot.inventory_categories,
        snapshot.inventory_items,
        snapshot.inventory_movements,
        snapshot.service_contracts,
        snapshot.service_order_images,
        snapshot.role_change_requests,
        snapshot.temporary_permissions,
    )
    return snapshot


def tenant_slug(company_id: UUID) -> str:
    if not settings.USE_TENANT_DATABASE_ROUTING:
        return "default"
    with catalog_session_scope() as catalog_db:
        row = catalog_db.query(TenantRouting).filter(TenantRouting.company_id == company_id).first()
        return row.slug if row else "unknown"


def attach_license(
    ctx: SyncContext,
    snapshot: AdminSyncSnapshot,
    *,
    installation_id: str | None,
    hostname: str | None,
) -> AdminSyncSnapshot:
    if not installation_id:
        return snapshot
    company = ctx.db.query(Company).filter(Company.id == ctx.company_id).first()
    if not company:
        return snapshot
    seat_id = uuid4()
    if settings.USE_TENANT_DATABASE_ROUTING:
        with catalog_session_scope() as catalog_db:
            seat = record_installation_sync(
                catalog_db,
                company_id=ctx.company_id,
                installation_id=installation_id,
                hostname=hostname,
                plan_code=company.plan.value,
            )
            catalog_db.commit()
            seat_id = seat.id
    signed = build_license_manifest(
        ctx.db,
        company=company,
        tenant_slug=tenant_slug(ctx.company_id),
        seat_id=seat_id,
        installation_id=installation_id,
    )
    snapshot.license_manifest = signed
    return snapshot
