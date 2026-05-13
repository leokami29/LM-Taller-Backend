from typing import Optional, Union
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import SecurityUtils, TYP_PLATFORM
from app.db.catalog.models import CatalogPlatformUser
from app.db.models.platform_user import PlatformUser


def authenticate_platform_user(
    db: Session, email: str, password: str
) -> Optional[Union[PlatformUser, CatalogPlatformUser]]:
    model = CatalogPlatformUser if settings.USE_TENANT_DATABASE_ROUTING else PlatformUser
    u = db.query(model).filter(model.email == email).first()
    if not u:
        return None
    if not SecurityUtils.verify_password(password, u.hashed_password):
        return None
    return u


def create_platform_token_pair(
    user: PlatformUser | CatalogPlatformUser, act_as_company_id: Optional[UUID] = None
) -> tuple[str, str]:
    access = SecurityUtils.create_platform_access_token(
        user.id, user.role.value, act_as_company_id=act_as_company_id
    )
    refresh = SecurityUtils.create_platform_refresh_token(
        user.id, user.role.value, act_as_company_id=act_as_company_id
    )
    return access, refresh


def refresh_platform_tokens(
    db: Session, refresh_token: str
) -> Optional[tuple[str, str, Union[PlatformUser, CatalogPlatformUser]]]:
    payload = SecurityUtils.decode_token(refresh_token)
    if not payload or payload.get("token_use") != "refresh":
        return None
    if payload.get("rtyp") != TYP_PLATFORM and payload.get("typ") != TYP_PLATFORM:
        return None
    try:
        uid = UUID(str(payload.get("sub")))
    except (TypeError, ValueError):
        return None
    model = CatalogPlatformUser if settings.USE_TENANT_DATABASE_ROUTING else PlatformUser
    user = db.query(model).filter(model.id == uid).first()
    if not user or not user.is_active:
        return None
    act_as: Optional[UUID] = None
    raw_act = payload.get("act_as_company_id")
    if raw_act:
        try:
            act_as = UUID(str(raw_act))
        except (TypeError, ValueError):
            return None
    return (*create_platform_token_pair(user, act_as_company_id=act_as), user)
