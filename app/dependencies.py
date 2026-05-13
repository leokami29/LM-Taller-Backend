from typing import Callable, Iterable
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.enums import PlatformRole, UserRole
from app.core.permissions import platform_has_permission, tenant_has_permission
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


class RequirePermission:
    """Dependencia: exige permiso tenant recurso:acción."""

    def __init__(self, permission: str) -> None:
        self.permission = permission

    def __call__(self, user: User = Depends(get_current_user)) -> User:
        if not tenant_has_permission(user.role, self.permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permiso requerido: {self.permission}",
            )
        return user


def ensure_not_viewer_for_mutation(user: User) -> None:
    if user.role == UserRole.VIEWER:
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
