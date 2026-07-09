from typing import Callable, Iterable
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.enums import UserRole
from app.core.security import (
    TOKEN_USE_ACCESS,
    TYP_PLATFORM,
    TYP_PORTAL,
    SecurityUtils,
    oauth2_scheme,
)
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
    if payload.get("typ") in (TYP_PLATFORM, TYP_PORTAL):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usa el token de empresa en /api/v1, portal en /api/v1/portal o plataforma en /api/platform/v1",
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
