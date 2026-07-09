from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Generator
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.enums import UserRole
from app.core.permissions import ADMIN_USERS
from app.core.security import TOKEN_USE_ACCESS, TYP_TENANT, SecurityUtils, oauth2_scheme
from app.core.subscription_lifecycle import subscription_is_usable
from app.db.models.user import User
from app.db.session import tenant_session_for_company
from app.schemas.sync_admin import SyncContext
from app.services.permission_service import PermissionService


def get_sync_context(token: str = Depends(oauth2_scheme)) -> Generator[SyncContext, None, None]:
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


def ensure_subscription_allows_sync(ctx: SyncContext) -> None:
    svc = PermissionService(ctx.db)
    ent = svc.get_entitlements(ctx.company_id)
    period_end = svc.get_subscription_period_end(ctx.company_id)
    if not subscription_is_usable(ent.status, period_end):
        raise HTTPException(status_code=403, detail="La suscripcion no permite sincronizar")


def ensure_subscription_allows_push(ctx: SyncContext) -> None:
    svc = PermissionService(ctx.db)
    ent = svc.get_entitlements(ctx.company_id)
    period_end = svc.get_subscription_period_end(ctx.company_id)
    if not subscription_is_usable(ent.status, period_end):
        raise HTTPException(status_code=403, detail="La suscripcion no permite sincronizar cambios")
