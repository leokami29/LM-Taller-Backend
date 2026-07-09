from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.enums import PlatformRole
from app.core.permissions import platform_has_permission
from app.core.security import (
    TOKEN_USE_ACCESS,
    TYP_PLATFORM,
    SecurityUtils,
    platform_oauth2_scheme,
)
from app.db.catalog.models import CatalogPlatformUser
from app.db.models.platform_user import PlatformUser
from app.db.session import get_db


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
