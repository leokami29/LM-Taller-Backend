"""Autorización: plan ∩ rol por sede ∪ permisos temporales."""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dt import utc_now
from app.core.entitlements import Entitlements
from app.core.enums import UserRole
from app.core.features import permission_to_module
from app.core.permissions import TENANT_ROLE_PERMISSIONS, tenant_has_permission
from app.core.subscription_lifecycle import subscription_is_usable
from app.db.models.audit_log import AuditLog
from app.db.models.company import Company
from app.db.models.rbac import Site, TemporaryPermission, UserSiteRole
from app.db.models.service_order import ServiceOrder
from app.db.models.user import User


def get_catalog_subscription_period_end(company_id: UUID) -> datetime | None:
    from app.config import settings

    if not settings.USE_TENANT_DATABASE_ROUTING:
        return None
    from app.db.catalog.models import Subscription
    from app.db.session import catalog_session_scope

    with catalog_session_scope() as catalog_db:
        sub = catalog_db.query(Subscription).filter(Subscription.company_id == company_id).first()
        return sub.current_period_end if sub else None


class PermissionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_entitlements(self, company_id: UUID) -> Entitlements:
        company = self.db.query(Company).filter(Company.id == company_id).first()
        if not company:
            return Entitlements.default_starter()
        from app.config import settings
        from app.services.effective_entitlements_service import resolve_effective_entitlements

        if settings.USE_TENANT_DATABASE_ROUTING:
            return resolve_effective_entitlements(company)
        return Entitlements.from_company_row(
            plan=company.plan,
            subscription_status=company.subscription_status,
            active_users_limit=company.active_users_limit,
            settings_json=company.settings_json,
        )

    def get_subscription_period_end(self, company_id: UUID) -> datetime | None:
        return get_catalog_subscription_period_end(company_id)

    def get_billing_email(self, company_id: UUID) -> str | None:
        company = self.db.query(Company).filter(Company.id == company_id).first()
        return company.billing_email if company else None

    def is_company_subscription_usable(self, company_id: UUID) -> bool:
        ent = self.get_entitlements(company_id)
        period_end = self.get_subscription_period_end(company_id)
        return subscription_is_usable(ent.status, period_end)

    def has_company_wide_role(self, user_id: UUID, company_id: UUID) -> bool:
        return (
            self.db.query(UserSiteRole)
            .filter(
                UserSiteRole.user_id == user_id,
                UserSiteRole.company_id == company_id,
                UserSiteRole.site_id.is_(None),
                UserSiteRole.is_active.is_(True),
            )
            .first()
            is not None
        )

    def has_any_site_role(self, user_id: UUID, company_id: UUID) -> bool:
        return (
            self.db.query(UserSiteRole)
            .filter(
                UserSiteRole.user_id == user_id,
                UserSiteRole.company_id == company_id,
                UserSiteRole.site_id.isnot(None),
                UserSiteRole.is_active.is_(True),
            )
            .first()
            is not None
        )

    def resolve_role_for_site(
        self,
        user_id: UUID,
        company_id: UUID,
        site_id: UUID | None,
    ) -> UserRole | None:
        q = (
            self.db.query(UserSiteRole)
            .filter(
                UserSiteRole.user_id == user_id,
                UserSiteRole.company_id == company_id,
                UserSiteRole.is_active.is_(True),
            )
        )
        if site_id is not None:
            row = q.filter(UserSiteRole.site_id == site_id).first()
            if row is None:
                row = q.filter(UserSiteRole.site_id.is_(None)).first()
            if row:
                return row.role
            return None

        # Sin sede activa: solo rol de empresa (site_id NULL). Nunca promover un rol de otra sede.
        row = q.filter(UserSiteRole.site_id.is_(None)).first()
        if row:
            return row.role
        # Compatibilidad: usuarios sin filas UserSiteRole usan el rol legado en users.role
        # únicamente si no tienen roles acotados a sede.
        if self.has_any_site_role(user_id, company_id):
            return None
        user = self.db.query(User).filter(User.id == user_id, User.company_id == company_id).first()
        return user.role if user else None

    def _active_temporary_permissions(
        self,
        user_id: UUID,
        company_id: UUID,
        site_id: UUID | None,
    ) -> set[str]:
        now = utc_now()
        rows = (
            self.db.query(TemporaryPermission)
            .filter(
                TemporaryPermission.user_id == user_id,
                TemporaryPermission.company_id == company_id,
                TemporaryPermission.expires_at > now,
            )
            .all()
        )
        out: set[str] = set()
        for row in rows:
            # Permiso de sede solo aplica con X-Site-Id coincidente; nunca se eleva a global.
            if row.site_id is None:
                out.add(row.permission)
            elif site_id is not None and row.site_id == site_id:
                out.add(row.permission)
        return out

    def get_user_permissions(
        self,
        user_id: UUID,
        company_id: UUID,
        site_id: UUID | None = None,
    ) -> frozenset[str]:
        if not self.is_company_subscription_usable(company_id):
            return frozenset()

        ent = self.get_entitlements(company_id)
        role = self.resolve_role_for_site(user_id, company_id, site_id)
        if role is None:
            return frozenset()

        base = {
            p
            for p in TENANT_ROLE_PERMISSIONS.get(role, frozenset())
            if ent.has_module(permission_to_module(p))
        }
        for perm in self._active_temporary_permissions(user_id, company_id, site_id):
            if ent.has_module(permission_to_module(perm)):
                base.add(perm)
        return frozenset(base)

    def has_permission(
        self,
        user_id: UUID,
        company_id: UUID,
        permission: str,
        site_id: UUID | None = None,
    ) -> bool:
        if not self.is_company_subscription_usable(company_id):
            return False
        ent = self.get_entitlements(company_id)
        if not ent.has_module(permission_to_module(permission)):
            return False
        if permission in self._active_temporary_permissions(user_id, company_id, site_id):
            return True
        role = self.resolve_role_for_site(user_id, company_id, site_id)
        if role is None:
            return False
        return tenant_has_permission(role, permission)

    def user_has_site_access(self, user_id: UUID, company_id: UUID, site_id: UUID) -> bool:
        exists = (
            self.db.query(UserSiteRole)
            .filter(
                UserSiteRole.user_id == user_id,
                UserSiteRole.company_id == company_id,
                UserSiteRole.is_active.is_(True),
                (UserSiteRole.site_id == site_id) | (UserSiteRole.site_id.is_(None)),
            )
            .first()
        )
        return exists is not None

    def list_accessible_sites(self, user_id: UUID, company_id: UUID) -> list[Site]:
        global_role = (
            self.db.query(UserSiteRole)
            .filter(
                UserSiteRole.user_id == user_id,
                UserSiteRole.company_id == company_id,
                UserSiteRole.site_id.is_(None),
                UserSiteRole.is_active.is_(True),
            )
            .first()
        )
        if global_role:
            return (
                self.db.query(Site)
                .filter(Site.company_id == company_id, Site.is_active.is_(True))
                .order_by(Site.name)
                .all()
            )
        site_ids = [
            r.site_id
            for r in self.db.query(UserSiteRole)
            .filter(
                UserSiteRole.user_id == user_id,
                UserSiteRole.company_id == company_id,
                UserSiteRole.site_id.isnot(None),
                UserSiteRole.is_active.is_(True),
            )
            .all()
            if r.site_id
        ]
        if not site_ids:
            return []
        return (
            self.db.query(Site)
            .filter(Site.id.in_(site_ids), Site.is_active.is_(True))
            .order_by(Site.name)
            .all()
        )

    def count_active_users(self, company_id: UUID) -> int:
        return (
            self.db.query(func.count(User.id))
            .filter(User.company_id == company_id, User.is_active.is_(True))
            .scalar()
            or 0
        )

    def count_orders_current_month(self, company_id: UUID) -> int:
        now = utc_now()
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_day = monthrange(now.year, now.month)[1]
        end = now.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)
        return (
            self.db.query(func.count(ServiceOrder.id))
            .filter(
                ServiceOrder.company_id == company_id,
                ServiceOrder.created_at >= start,
                ServiceOrder.created_at <= end,
            )
            .scalar()
            or 0
        )

    def can_add_user(self, company_id: UUID) -> tuple[bool, str]:
        if not self.is_company_subscription_usable(company_id):
            return False, "Suscripción inactiva o período vencido"
        ent = self.get_entitlements(company_id)
        limit = ent.max_users
        if limit is None:
            return True, ""
        count = self.count_active_users(company_id)
        if count >= limit:
            return False, f"Límite de usuarios del plan alcanzado ({limit})"
        return True, ""

    def can_create_order(self, company_id: UUID) -> tuple[bool, str]:
        if not self.is_company_subscription_usable(company_id):
            return False, "Suscripción inactiva o período vencido"
        ent = self.get_entitlements(company_id)
        if not ent.has_module("orders"):
            return False, "Módulo de órdenes no incluido en el plan"
        limit = ent.max_orders_month
        if limit is None:
            return True, ""
        count = self.count_orders_current_month(company_id)
        if count >= limit:
            return False, f"Límite mensual de órdenes alcanzado ({limit})"
        return True, ""

    def log_action(
        self,
        *,
        user_id: UUID,
        company_id: UUID,
        action: str,
        resource: str,
        resource_id: UUID | None = None,
        changes: dict[str, Any] | None = None,
        request: Request | None = None,
        site_id: UUID | None = None,
    ) -> None:
        ip_address = None
        user_agent = None
        if request is not None:
            ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent")
        entry = AuditLog(
            actor_type="tenant",
            actor_id=str(user_id),
            company_id=company_id,
            user_id=user_id,
            site_id=site_id,
            action=action,
            resource_type=resource,
            resource_id=str(resource_id) if resource_id else None,
            metadata_json={"changes": changes} if changes else {},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(entry)
        self.db.commit()
