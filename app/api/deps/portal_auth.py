from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import (
    TOKEN_USE_ACCESS,
    TYP_PORTAL,
    SecurityUtils,
    portal_oauth2_scheme,
)
from app.db.models.customer_portal_user import CustomerPortalUser
from app.db.session import get_db


@dataclass
class PortalContext:
    user: CustomerPortalUser
    portal_user_id: UUID
    company_id: UUID
    customer_id: UUID


def get_current_portal_user(
    token: str = Depends(portal_oauth2_scheme),
    db: Session = Depends(get_db),
) -> CustomerPortalUser:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales de portal no válidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = SecurityUtils.decode_token(token)
    if not payload or payload.get("token_use") not in (None, TOKEN_USE_ACCESS):
        raise exc
    if payload.get("typ") != TYP_PORTAL:
        raise exc
    try:
        uid = UUID(str(payload.get("sub")))
        cid = UUID(str(payload.get("company_id")))
        cust_id = UUID(str(payload.get("customer_id")))
    except (TypeError, ValueError):
        raise exc
    user = db.query(CustomerPortalUser).filter(CustomerPortalUser.id == uid).first()
    if user is None or not user.is_active:
        raise exc
    if user.company_id != cid or user.customer_id != cust_id:
        raise exc
    return user


def get_portal_context(
    user: CustomerPortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_db),
) -> PortalContext:
    from app.services.portal_auth_service import assert_portal_module_enabled

    try:
        assert_portal_module_enabled(db, user.company_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    return PortalContext(
        user=user,
        portal_user_id=user.id,
        company_id=user.company_id,
        customer_id=user.customer_id,
    )
