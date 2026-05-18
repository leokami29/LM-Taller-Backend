"""Perfil y permisos del usuario autenticado."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.features import MODULE_CORE
from app.core.subscription_lifecycle import subscription_block_reason, subscription_is_usable
from app.dependencies import PermissionContext, get_current_user, get_permission_context
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.rbac import (
    EntitlementsLimits,
    EntitlementsPayload,
    EntitlementsUsage,
    MePermissionsResponse,
    SiteResponse,
)
from app.services.permission_service import PermissionService

router = APIRouter(tags=["me"])


@router.get("/me/permissions", response_model=MePermissionsResponse)
def get_my_permissions(
    site_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MePermissionsResponse:
    svc = PermissionService(db)
    effective_site = site_id
    if effective_site is not None and not svc.user_has_site_access(user.id, user.company_id, effective_site):
        effective_site = None
    role = svc.resolve_role_for_site(user.id, user.company_id, effective_site)
    perms = svc.get_user_permissions(user.id, user.company_id, effective_site)
    sites = svc.list_accessible_sites(user.id, user.company_id)
    ent = svc.get_entitlements(user.company_id)
    period_end = svc.get_subscription_period_end(user.company_id)
    usable = subscription_is_usable(ent.status, period_end)
    block_reason = subscription_block_reason(ent.status, period_end)
    modules = sorted(m for m in ent.modules if m != MODULE_CORE)
    return MePermissionsResponse(
        role=role or user.role,
        site_id=effective_site,
        permissions=sorted(perms),
        sites=[SiteResponse.model_validate(s) for s in sites],
        entitlements=EntitlementsPayload(
            plan=ent.plan.value,
            status=ent.status.value,
            modules=modules,
            limits=EntitlementsLimits(
                max_users=ent.max_users,
                max_orders_month=ent.max_orders_month,
                storage_mb=ent.storage_mb,
            ),
            usage=EntitlementsUsage(
                users=svc.count_active_users(user.company_id),
                orders_month=svc.count_orders_current_month(user.company_id),
                storage_mb=0,
            ),
            subscription_usable=usable,
            subscription_block_reason=block_reason,
            current_period_end=period_end,
            billing_email=svc.get_billing_email(user.company_id),
        ),
    )
