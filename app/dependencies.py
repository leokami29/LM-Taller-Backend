from dataclasses import dataclass
from typing import Callable, Iterable
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.enums import PlatformRole, UserRole
from app.core.permissions import platform_has_permission
from app.services.permission_service import PermissionService
from app.core.security import (
    TYP_PLATFORM,
    TYP_TENANT,
    TOKEN_USE_ACCESS,
    SecurityUtils,
    oauth2_scheme,
    platform_oauth2_scheme,
)
from app.config import settings
from app.db.catalog.models import CatalogPlatformUser
from app.db.models.platform_user import PlatformUser
from app.db.models.user import User
from app.db.session import get_db


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = SecurityUtils.decode_token(token)
    if payload is None:
        raise credentials_exception
    if payload.get("token_use") not in (None, TOKEN_USE_ACCESS):
        raise credentials_exception
    if payload.get("typ") == TYP_PLATFORM:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usa el token de empresa en /api/v1 o el panel /api/platform/v1",
        )
    sub = payload.get("sub")
    if sub is None:
        raise credentials_exception
    try:
        user_id = UUID(str(sub))
    except ValueError as exc:
        raise credentials_exception from exc

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise credentials_exception

    token_company = payload.get("company_id")
    if token_company is not None:
        if str(user.company_id) != str(token_company):
            raise credentials_exception
    return user


def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren permisos de administrador",
        )
    return current_user


def get_current_technician_or_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in (UserRole.ADMIN, UserRole.TECHNICIAN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren permisos de técnico o administrador",
        )
    return current_user


def require_roles(*roles: UserRole) -> Callable[..., User]:
    allowed: Iterable[UserRole] = roles

    def _dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permisos insuficientes para esta operación",
            )
        return user

    return _dependency


@dataclass
class PermissionContext:
    user: User
    user_id: UUID
    company_id: UUID
    site_id: UUID | None
    role: UserRole
    permissions: frozenset[str]


def _parse_site_id(raw: str | None) -> UUID | None:
    if not raw or not raw.strip():
        return None
    try:
        return UUID(raw.strip())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Site-Id inválido") from exc


def get_permission_context(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    x_site_id: str | None = Header(None, alias="X-Site-Id"),
    site_id_query: UUID | None = None,
) -> PermissionContext:
    svc = PermissionService(db)
    site_id = _parse_site_id(x_site_id)
    if site_id is None and site_id_query is not None:
        site_id = site_id_query
    if site_id is not None and not svc.user_has_site_access(user.id, user.company_id, site_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin acceso a esta sede")
    role = svc.resolve_role_for_site(user.id, user.company_id, site_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rol no asignado")
    perms = svc.get_user_permissions(user.id, user.company_id, site_id)
    return PermissionContext(
        user=user,
        user_id=user.id,
        company_id=user.company_id,
        site_id=site_id,
        role=role,
        permissions=perms,
    )


class RequirePermission:
    """Dependencia: exige permiso tenant recurso:acción (plan ∩ rol sede ∪ temporales)."""

    def __init__(self, permission: str) -> None:
        self.permission = permission

    def __call__(self, ctx: PermissionContext = Depends(get_permission_context)) -> User:
        if self.permission not in ctx.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permiso requerido: {self.permission}",
            )
        return ctx.user


def ensure_not_viewer_for_mutation(subject: User | PermissionContext) -> None:
    role = subject.role if isinstance(subject, PermissionContext) else subject.role
    if role == UserRole.VIEWER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El rol viewer solo puede consultar",
        )


def get_current_platform_user(
    token: str = Depends(platform_oauth2_scheme),
    db: Session = Depends(get_db),
) -> PlatformUser:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales de plataforma no válidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = SecurityUtils.decode_token(token)
    if not payload or payload.get("token_use") not in (None, TOKEN_USE_ACCESS):
        raise exc
    if payload.get("typ") != TYP_PLATFORM:
        raise exc
    try:
        uid = UUID(str(payload.get("sub")))
    except (TypeError, ValueError):
        raise exc
    model = CatalogPlatformUser if settings.USE_TENANT_DATABASE_ROUTING else PlatformUser
    user = db.query(model).filter(model.id == uid).first()
    if user is None or not user.is_active:
        raise exc
    return user


class RequirePlatformPermission:
    def __init__(self, permission: str) -> None:
        self.permission = permission

    def __call__(self, user: PlatformUser = Depends(get_current_platform_user)) -> PlatformUser:
        if not platform_has_permission(user.role, self.permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permiso de plataforma requerido: {self.permission}",
            )
        return user


def require_platform_super_admin(
    user: PlatformUser = Depends(get_current_platform_user),
) -> PlatformUser:
    if user.role != PlatformRole.SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo super administrador")
    return user
