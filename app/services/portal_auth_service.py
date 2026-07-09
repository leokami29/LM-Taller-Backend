from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.dt import utc_now
from app.core.features import MODULE_CUSTOMER_PORTAL
from app.core.security import TYP_PORTAL, SecurityUtils
from app.db.models.company import Company
from app.db.models.customer_portal_user import CustomerPortalUser
from app.services.permission_service import PermissionService


def authenticate_portal_user(db: Session, email: str, password: str) -> Optional[CustomerPortalUser]:
    user = (
        db.query(CustomerPortalUser)
        .filter(CustomerPortalUser.email == email, CustomerPortalUser.is_active.is_(True))
        .first()
    )
    if not user:
        return None
    if not SecurityUtils.verify_password(password, user.hashed_password):
        return None
    return user


def assert_portal_module_enabled(db: Session, company_id) -> Company:
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise ValueError("Empresa no encontrada")
    ent = PermissionService(db).get_entitlements(company_id)
    if not ent.has_module(MODULE_CUSTOMER_PORTAL):
        raise ValueError("El portal de clientes no está habilitado en su plan")
    if not ent.is_subscription_usable():
        raise ValueError("La suscripción del taller no está activa")
    return company


def create_portal_token_pair(user: CustomerPortalUser, db: Session) -> tuple[str, str]:
    assert_portal_module_enabled(db, user.company_id)
    access = SecurityUtils.create_portal_access_token(user.id, user.company_id, user.customer_id)
    refresh = SecurityUtils.create_portal_refresh_token(user.id, user.company_id, user.customer_id)
    user.last_login = utc_now()
    db.add(user)
    return access, refresh


def refresh_portal_tokens(
    db: Session,
    refresh_token: str,
) -> Optional[tuple[str, str, CustomerPortalUser]]:
    payload = SecurityUtils.decode_token(refresh_token)
    if not payload or payload.get("token_use") != "refresh":
        return None
    if payload.get("rtyp") != TYP_PORTAL and payload.get("typ") != TYP_PORTAL:
        return None
    try:
        uid = UUID(str(payload.get("sub")))
        cid = UUID(str(payload.get("company_id")))
        cust_id = UUID(str(payload.get("customer_id")))
    except (TypeError, ValueError):
        return None
    user = db.query(CustomerPortalUser).filter(CustomerPortalUser.id == uid).first()
    if not user or not user.is_active or user.company_id != cid or user.customer_id != cust_id:
        return None
    assert_portal_module_enabled(db, user.company_id)
    access = SecurityUtils.create_portal_access_token(user.id, user.company_id, user.customer_id)
    refresh = SecurityUtils.create_portal_refresh_token(user.id, user.company_id, user.customer_id)
    return access, refresh, user


def create_portal_user(
    db: Session,
    *,
    company_id,
    customer_id,
    email: str,
    full_name: str,
    password: str,
    invited_by_id,
) -> CustomerPortalUser:
    from app.services.contract_service import _assert_customer

    assert_portal_module_enabled(db, company_id)
    _assert_customer(db, company_id=company_id, customer_id=customer_id)
    clash = (
        db.query(CustomerPortalUser.id)
        .filter(CustomerPortalUser.company_id == company_id, CustomerPortalUser.email == email)
        .first()
    )
    if clash:
        raise ValueError("Ya existe un usuario portal con ese email")
    row = CustomerPortalUser(
        company_id=company_id,
        customer_id=customer_id,
        email=email.strip().lower(),
        full_name=full_name.strip(),
        hashed_password=SecurityUtils.hash_password(password),
        invited_by_id=invited_by_id,
    )
    db.add(row)
    db.flush()
    return row
