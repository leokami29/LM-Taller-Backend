"""Sincronizacion administrativa para SGtaller Desktop.

Estos endpoints son aditivos y trabajan solo sobre el tenant del JWT recibido.
Aunque `get_db` ya sabe resolver data planes en modo routing, este modulo abre
explicitamente la sesion con `tenant_session_for_company(company_id)` para que el
contrato de desktop sea claro y testeable.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.core.dt import utc_now
from app.core.enums import SubscriptionStatus, UserRole
from app.core.permissions import ADMIN_USERS
from app.core.security import TOKEN_USE_ACCESS, TYP_TENANT, SecurityUtils, oauth2_scheme
from app.core.subscription_lifecycle import subscription_is_usable, validate_subscription_period_status
from app.db.catalog.models import TenantRouting
from app.db.models.company import Company
from app.db.models.customer import Customer
from app.db.models.equipment import Equipment
from app.db.models.inventory import InventoryItem, InventoryMovement
from app.db.models.service_contract import ServiceContract
from app.db.models.service_order import ServiceOrder
from app.db.models.rbac import Site, UserSiteRole
from app.db.models.user import User
from app.db.session import catalog_session_scope, tenant_session_for_company
from app.schemas.license import SignedLicenseManifest
from app.services.installation_service import record_installation_sync, register_or_touch_installation
from app.services.license_manifest_service import build_license_manifest
from app.services.permission_service import PermissionService
from app.services.tenant_config_events import (
    TenantConfigReason,
    bump_company_config_revision,
    notify_company_config_changed,
)

router = APIRouter(prefix="/sync/admin", tags=["sync-admin"])

SyncEntity = Literal["company", "site", "user", "user_site_role", "session_policy"]
SyncOp = Literal["create", "update", "delete", "deactivate", "reset_password"]


class AdminMutation(BaseModel):
    mutation_id: UUID = Field(default_factory=uuid4)
    entity: SyncEntity
    entity_id: UUID
    op: SyncOp
    updated_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class AdminPushRequest(BaseModel):
    mutations: list[AdminMutation] = Field(default_factory=list)
    

class AdminPushItemResult(BaseModel):
    mutation_id: UUID
    entity: SyncEntity
    entity_id: UUID
    status: Literal["applied", "rejected", "conflict"]
    detail: str = ""


class AdminPushResponse(BaseModel):
    results: list[AdminPushItemResult]
    cursor: str


class AdminSyncSnapshot(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    company_id: UUID
    cursor: str
    company: dict[str, Any]
    sites: list[dict[str, Any]]
    users: list[dict[str, Any]]
    user_site_roles: list[dict[str, Any]]
    entitlements: dict[str, Any]
    license_manifest: SignedLicenseManifest | None = None
    customers: list[dict[str, Any]] = Field(default_factory=list)
    equipment: list[dict[str, Any]] = Field(default_factory=list)
    service_orders: list[dict[str, Any]] = Field(default_factory=list)
    inventory_items: list[dict[str, Any]] = Field(default_factory=list)
    inventory_movements: list[dict[str, Any]] = Field(default_factory=list)
    service_contracts: list[dict[str, Any]] = Field(default_factory=list)


@dataclass
class SyncContext:
    db: Session
    user: User
    company_id: UUID
    permissions: frozenset[str]


def _max_cursor(*groups: list[dict[str, Any]]) -> str:
    values = [
        item.get("updated_at")
        for group in groups
        for item in group
        if item.get("updated_at") is not None
    ]
    if not values:
        return utc_now().isoformat()
    return max(str(v) for v in values)


def _row(model: Any) -> dict[str, Any]:
    return jsonable_encoder(model)


def _sync_context(token: str = Depends(oauth2_scheme)):
    payload = SecurityUtils.decode_token(token)
    if not payload or payload.get("token_use") not in (None, TOKEN_USE_ACCESS):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token de empresa invalido")
    if payload.get("typ") not in (None, TYP_TENANT):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usa un token tenant")
    try:
        user_id = UUID(str(payload.get("sub")))
        company_id = UUID(str(payload.get("company_id")))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token de empresa incompleto") from exc

    session_cm: AbstractContextManager[Session] = tenant_session_for_company(company_id)
    with session_cm as db:
        user = db.query(User).filter(User.id == user_id, User.company_id == company_id).first()
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario inactivo o inexistente")
        svc = PermissionService(db)
        permissions = svc.get_user_permissions(user.id, company_id, None)
        if ADMIN_USERS not in permissions and user.role != UserRole.ADMIN:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permiso requerido: {ADMIN_USERS}")
        yield SyncContext(db=db, user=user, company_id=company_id, permissions=permissions)


def _snapshot(ctx: SyncContext) -> AdminSyncSnapshot:
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
    customers = ctx.db.query(Customer).filter(Customer.company_id == ctx.company_id).order_by(Customer.created_at.desc()).all()
    equipment = ctx.db.query(Equipment).filter(Equipment.company_id == ctx.company_id).order_by(Equipment.created_at.desc()).all()
    orders = ctx.db.query(ServiceOrder).filter(ServiceOrder.company_id == ctx.company_id).order_by(ServiceOrder.created_at.desc()).all()
    inv_items = ctx.db.query(InventoryItem).filter(InventoryItem.company_id == ctx.company_id).order_by(InventoryItem.created_at.desc()).all()
    inv_item_ids = [i.id for i in inv_items]
    inv_movements = (
        ctx.db.query(InventoryMovement)
        .filter(InventoryMovement.inventory_item_id.in_(inv_item_ids))
        .order_by(InventoryMovement.moved_at.desc())
        .all()
    ) if inv_item_ids else []
    contracts = ctx.db.query(ServiceContract).filter(ServiceContract.company_id == ctx.company_id).order_by(ServiceContract.created_at.desc()).all()
    svc = PermissionService(ctx.db)
    ent = svc.get_entitlements(ctx.company_id)
    period_end = svc.get_subscription_period_end(ctx.company_id)
    site_rows = [_row(s) for s in sites]
    user_rows = [_row(u) for u in users]
    role_rows = [_row(r) for r in roles]
    company_row = _row(company)
    customer_rows = [_row(c) for c in customers]
    equipment_rows = [_row(e) for e in equipment]
    order_rows = [_row(o) for o in orders]
    item_rows = [_row(i) for i in inv_items]
    movement_rows = [_row(m) for m in inv_movements]
    contract_rows = [_row(c) for c in contracts]
    return AdminSyncSnapshot(
        company_id=ctx.company_id,
        cursor=_max_cursor(
            [company_row], site_rows, user_rows, role_rows,
            customer_rows, equipment_rows, order_rows, item_rows, movement_rows, contract_rows,
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
        service_orders=order_rows,
        inventory_items=item_rows,
        inventory_movements=movement_rows,
        service_contracts=contract_rows,
    )


def _ensure_subscription_allows_sync(ctx: SyncContext) -> None:
    svc = PermissionService(ctx.db)
    ent = svc.get_entitlements(ctx.company_id)
    period_end = svc.get_subscription_period_end(ctx.company_id)
    if not subscription_is_usable(ent.status, period_end):
        raise HTTPException(status_code=403, detail="La suscripcion no permite sincronizar")


def _ensure_subscription_allows_push(ctx: SyncContext) -> None:
    svc = PermissionService(ctx.db)
    ent = svc.get_entitlements(ctx.company_id)
    period_end = svc.get_subscription_period_end(ctx.company_id)
    if not subscription_is_usable(ent.status, period_end):
        raise HTTPException(status_code=403, detail="La suscripcion no permite sincronizar cambios")


def _as_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _reject_if_stale(existing: Any, mutation: AdminMutation) -> AdminPushItemResult | None:
    current = getattr(existing, "updated_at", None)
    if current is not None and _as_utc_aware(current) > _as_utc_aware(mutation.updated_at):
        return AdminPushItemResult(
            mutation_id=mutation.mutation_id,
            entity=mutation.entity,
            entity_id=mutation.entity_id,
            status="conflict",
            detail="El servidor tiene una version mas reciente",
        )
    return None


def _load_company_or_reject(ctx: SyncContext, mutation: AdminMutation) -> tuple[Company | None, AdminPushItemResult | None]:
    """Fetch company + staleness check shared by _apply_company and _apply_session_policy."""
    company = ctx.db.query(Company).filter(Company.id == ctx.company_id).first()
    if not company:
        return None, _rejected(mutation, "Empresa no encontrada")
    conflict = _reject_if_stale(company, mutation)
    if conflict:
        return None, conflict
    return company, None


def _apply_company(ctx: SyncContext, mutation: AdminMutation) -> AdminPushItemResult:
    company, rejection = _load_company_or_reject(ctx, mutation)
    if rejection:
        return rejection
    if mutation.op not in ("update",):
        return _rejected(mutation, "Operacion no soportada para company")
    if "subscription_status" in mutation.payload or "current_period_end" in mutation.payload:
        try:
            status_value = SubscriptionStatus(mutation.payload.get("subscription_status", company.subscription_status))
            period_end = mutation.payload.get("current_period_end")
            if isinstance(period_end, str):
                period_end = datetime.fromisoformat(period_end)
            validate_subscription_period_status(status_value, period_end)
        except ValueError as exc:
            return _rejected(mutation, str(exc))
        return _rejected(mutation, "La suscripcion se administra desde plataforma")
    allowed = {"name", "address", "phone", "email", "country", "currency"}
    for key, value in mutation.payload.items():
        if key in allowed:
            setattr(company, key, value)
    company.updated_at = mutation.updated_at
    bump_company_config_revision(company)
    ctx.db.add(company)
    return _applied(mutation)


def _apply_session_policy(ctx: SyncContext, mutation: AdminMutation) -> AdminPushItemResult:
    company, rejection = _load_company_or_reject(ctx, mutation)
    if rejection:
        return rejection
    settings_json = dict(company.settings_json or {})
    settings_json["session_policies"] = mutation.payload.get("session_policies", {})
    company.settings_json = settings_json
    company.updated_at = mutation.updated_at
    bump_company_config_revision(company)
    ctx.db.add(company)
    return _applied(mutation)


def _apply_site(ctx: SyncContext, mutation: AdminMutation) -> AdminPushItemResult:
    site = ctx.db.query(Site).filter(Site.id == mutation.entity_id, Site.company_id == ctx.company_id).first()
    if mutation.op == "create":
        if site:
            return _applied(mutation)
        from app.services.site_code_service import derive_site_code, validate_site_code

        site_name = str(mutation.payload.get("name") or "Nueva sede")
        existing = {
            row[0]
            for row in ctx.db.query(Site.code).filter(Site.company_id == ctx.company_id).all()
        }
        raw_code = mutation.payload.get("code")
        code = (
            validate_site_code(str(raw_code))
            if raw_code
            else derive_site_code(site_name, existing)
        )
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
        return _applied(mutation)
    if not site:
        return _rejected(mutation, "Sede no encontrada")
    conflict = _reject_if_stale(site, mutation)
    if conflict:
        return conflict
    if mutation.op == "delete":
        site.is_active = False
    elif mutation.op == "update":
        for key in ("name", "location", "is_active"):
            if key in mutation.payload:
                setattr(site, key, mutation.payload[key])
    else:
        return _rejected(mutation, "Operacion no soportada para site")
    site.updated_at = mutation.updated_at
    ctx.db.add(site)
    return _applied(mutation)


def _apply_user(ctx: SyncContext, mutation: AdminMutation) -> AdminPushItemResult:
    user = ctx.db.query(User).filter(User.id == mutation.entity_id, User.company_id == ctx.company_id).first()
    if mutation.op == "create":
        if user:
            return _applied(mutation)
        ok, reason = PermissionService(ctx.db).can_add_user(ctx.company_id)
        if not ok:
            return _rejected(mutation, reason)
        password_hash = mutation.payload.get("hashed_password")
        if not password_hash:
            return _rejected(mutation, "hashed_password es obligatorio para crear usuario offline")
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
        return _applied(mutation)
    if not user:
        return _rejected(mutation, "Usuario no encontrado")
    conflict = _reject_if_stale(user, mutation)
    if conflict:
        return conflict
    if mutation.op == "deactivate":
        user.is_active = False
    elif mutation.op == "reset_password":
        if not mutation.payload.get("hashed_password"):
            return _rejected(mutation, "hashed_password es obligatorio")
        user.hashed_password = str(mutation.payload["hashed_password"])
    elif mutation.op == "update":
        for key in ("full_name", "phone", "is_active"):
            if key in mutation.payload:
                setattr(user, key, mutation.payload[key])
    else:
        return _rejected(mutation, "Operacion no soportada para user")
    user.updated_at = mutation.updated_at
    ctx.db.add(user)
    return _applied(mutation)


def _apply_user_site_role(ctx: SyncContext, mutation: AdminMutation) -> AdminPushItemResult:
    role = (
        ctx.db.query(UserSiteRole)
        .filter(UserSiteRole.id == mutation.entity_id, UserSiteRole.company_id == ctx.company_id)
        .first()
    )
    if mutation.op == "create":
        if role:
            return _applied(mutation)
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
        return _applied(mutation)
    if not role:
        return _rejected(mutation, "Rol de sede no encontrado")
    conflict = _reject_if_stale(role, mutation)
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
        return _rejected(mutation, "Operacion no soportada para user_site_role")
    role.updated_at = mutation.updated_at
    ctx.db.add(role)
    return _applied(mutation)


def _applied(mutation: AdminMutation) -> AdminPushItemResult:
    return AdminPushItemResult(
        mutation_id=mutation.mutation_id,
        entity=mutation.entity,
        entity_id=mutation.entity_id,
        status="applied",
    )


def _rejected(mutation: AdminMutation, detail: str) -> AdminPushItemResult:
    return AdminPushItemResult(
        mutation_id=mutation.mutation_id,
        entity=mutation.entity,
        entity_id=mutation.entity_id,
        status="rejected",
        detail=detail,
    )


def _tenant_slug(company_id: UUID) -> str:
    if not settings.USE_TENANT_DATABASE_ROUTING:
        return "default"
    with catalog_session_scope() as catalog_db:
        row = catalog_db.query(TenantRouting).filter(TenantRouting.company_id == company_id).first()
        return row.slug if row else "unknown"


def _attach_license(
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
        tenant_slug=_tenant_slug(ctx.company_id),
        seat_id=seat_id,
        installation_id=installation_id,
    )
    snapshot.license_manifest = signed
    return snapshot


@router.get("/bootstrap", response_model=AdminSyncSnapshot)
def bootstrap_admin(
    installation_id: Annotated[Optional[str], Query(min_length=8, max_length=128)] = None,
    hostname: Annotated[Optional[str], Query(max_length=255)] = None,
    ctx: SyncContext = Depends(_sync_context),
) -> AdminSyncSnapshot:
    _ensure_subscription_allows_sync(ctx)
    snap = _snapshot(ctx)
    return _attach_license(ctx, snap, installation_id=installation_id, hostname=hostname)


@router.get("/pull", response_model=AdminSyncSnapshot)
def pull_admin(
    since: datetime | None = Query(None),
    installation_id: Annotated[Optional[str], Query(min_length=8, max_length=128)] = None,
    hostname: Annotated[Optional[str], Query(max_length=255)] = None,
    ctx: SyncContext = Depends(_sync_context),
) -> AdminSyncSnapshot:
    _ensure_subscription_allows_sync(ctx)
    if since is None:
        snap = _snapshot(ctx)
        return _attach_license(ctx, snap, installation_id=installation_id, hostname=hostname)
    snapshot = _snapshot(ctx)
    snapshot.sites = [row for row in snapshot.sites if row.get("updated_at") and str(row["updated_at"]) > since.isoformat()]
    snapshot.users = [row for row in snapshot.users if row.get("updated_at") and str(row["updated_at"]) > since.isoformat()]
    snapshot.user_site_roles = [
        row for row in snapshot.user_site_roles if row.get("updated_at") and str(row["updated_at"]) > since.isoformat()
    ]
    snapshot.customers = [row for row in snapshot.customers if row.get("updated_at") and str(row["updated_at"]) > since.isoformat()]
    snapshot.equipment = [row for row in snapshot.equipment if row.get("updated_at") and str(row["updated_at"]) > since.isoformat()]
    snapshot.service_orders = [row for row in snapshot.service_orders if row.get("updated_at") and str(row["updated_at"]) > since.isoformat()]
    snapshot.inventory_items = [row for row in snapshot.inventory_items if row.get("updated_at") and str(row["updated_at"]) > since.isoformat()]
    snapshot.inventory_movements = [row for row in snapshot.inventory_movements if row.get("moved_at") and str(row["moved_at"]) > since.isoformat()]
    snapshot.service_contracts = [row for row in snapshot.service_contracts if row.get("updated_at") and str(row["updated_at"]) > since.isoformat()]
    if snapshot.company.get("updated_at") and str(snapshot.company["updated_at"]) <= since.isoformat():
        snapshot.company = {}
    snapshot.cursor = _max_cursor(
        [snapshot.company] if snapshot.company else [],
        snapshot.sites, snapshot.users, snapshot.user_site_roles,
        snapshot.customers, snapshot.equipment, snapshot.service_orders,
        snapshot.inventory_items, snapshot.inventory_movements, snapshot.service_contracts,
    )
    return _attach_license(ctx, snapshot, installation_id=installation_id, hostname=hostname)


@router.post("/push", response_model=AdminPushResponse)
def push_admin(
    payload: AdminPushRequest,
    installation_id: Annotated[Optional[str], Query(min_length=8, max_length=128)] = None,
    hostname: Annotated[Optional[str], Query(max_length=255)] = None,
    ctx: SyncContext = Depends(_sync_context),
) -> AdminPushResponse:
    _ensure_subscription_allows_push(ctx)
    results: list[AdminPushItemResult] = []
    for mutation in payload.mutations:
        if mutation.entity == "company":
            result = _apply_company(ctx, mutation)
        elif mutation.entity == "session_policy":
            result = _apply_session_policy(ctx, mutation)
        elif mutation.entity == "site":
            result = _apply_site(ctx, mutation)
        elif mutation.entity == "user":
            result = _apply_user(ctx, mutation)
        elif mutation.entity == "user_site_role":
            result = _apply_user_site_role(ctx, mutation)
        else:
            result = _rejected(mutation, "Entidad no soportada")
        results.append(result)
    ctx.db.commit()
    if any(r.status == "applied" for r in results):
        company = ctx.db.query(Company).filter(Company.id == ctx.company_id).first()
        if company:
            revision = bump_company_config_revision(company)
            ctx.db.add(company)
            ctx.db.commit()
            notify_company_config_changed(ctx.company_id, TenantConfigReason.COMPANY_STATUS, revision)
        if installation_id and settings.USE_TENANT_DATABASE_ROUTING:
            company_for_sync = ctx.db.query(Company).filter(Company.id == ctx.company_id).first()
            if company_for_sync:
                with catalog_session_scope() as catalog_db:
                    record_installation_sync(
                        catalog_db,
                        company_id=ctx.company_id,
                        installation_id=installation_id,
                        hostname=hostname,
                        plan_code=company_for_sync.plan.value,
                    )
                    catalog_db.commit()
    return AdminPushResponse(results=results, cursor=datetime.utcnow().isoformat())
