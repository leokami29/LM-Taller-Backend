from typing import Optional

from sqlalchemy.orm import Session

from app.core.security import SecurityUtils, TYP_TENANT
from app.db.models.user import User


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None
    if not SecurityUtils.verify_password(password, user.hashed_password):
        return None
    return user


def create_tenant_token_pair(user: User) -> tuple[str, str]:
    access = SecurityUtils.create_tenant_access_token(user.id, user.company_id)
    refresh = SecurityUtils.create_tenant_refresh_token(user.id, user.company_id)
    return access, refresh


def create_access_token_for_user(user: User) -> str:
    """Un solo access token (compat); preferir `create_tenant_token_pair`."""
    return SecurityUtils.create_tenant_access_token(user.id, user.company_id)


def refresh_tenant_tokens(db: Session, refresh_token: str) -> Optional[tuple[str, str, User]]:
    payload = SecurityUtils.decode_token(refresh_token)
    if not payload or payload.get("token_use") != "refresh":
        return None
    if payload.get("rtyp") != TYP_TENANT and payload.get("typ") != TYP_TENANT:
        return None
    from uuid import UUID

    try:
        uid = UUID(str(payload.get("sub")))
        cid = UUID(str(payload.get("company_id")))
    except (TypeError, ValueError):
        return None
    user = db.query(User).filter(User.id == uid).first()
    if not user or not user.is_active or user.company_id != cid:
        return None
    return (*create_tenant_token_pair(user), user)
