from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.security import TYP_TENANT, SecurityUtils
from app.db.models.company import Company
from app.db.models.user import User
from app.services.session_policy_service import ResolvedSession, resolve_tenant_session


def authenticate_user(db: Session, email: str, password: str, *, company_id: Optional[UUID] = None) -> Optional[User]:
    q = db.query(User).filter(User.email == email)
    if company_id:
        q = q.filter(User.company_id == company_id)
    user = q.first()
    if not user:
        return None
    if not SecurityUtils.verify_password(password, user.hashed_password):
        return None
    return user


def _load_company(db: Session, company_id: UUID) -> Company | None:
    return db.query(Company).filter(Company.id == company_id).first()


def create_tenant_token_pair(
    user: User,
    db: Session,
    *,
    site_id: UUID | None = None,
) -> tuple[str, str, ResolvedSession]:
    company = _load_company(db, user.company_id)
    if not company:
        raise ValueError("Empresa no encontrada")
    resolved = resolve_tenant_session(company, user_id=user.id, site_id=site_id)
    access = SecurityUtils.create_tenant_access_token(
        user.id, user.company_id, resolved=resolved
    )
    refresh = SecurityUtils.create_tenant_refresh_token(
        user.id, user.company_id, resolved=resolved
    )
    return access, refresh, resolved


def create_access_token_for_user(
    user: User,
    db: Session,
    *,
    site_id: UUID | None = None,
) -> str:
    """Un solo access token (compat); preferir `create_tenant_token_pair`."""
    access, _, _ = create_tenant_token_pair(user, db, site_id=site_id)
    return access


def refresh_tenant_tokens(
    db: Session,
    refresh_token: str,
    *,
    site_id: UUID | None = None,
) -> Optional[tuple[str, str, User, ResolvedSession]]:
    payload = SecurityUtils.decode_token(refresh_token)
    if not payload or payload.get("token_use") != "refresh":
        return None
    if payload.get("rtyp") != TYP_TENANT and payload.get("typ") != TYP_TENANT:
        return None

    try:
        uid = UUID(str(payload.get("sub")))
        cid = UUID(str(payload.get("company_id")))
    except (TypeError, ValueError):
        return None
    user = db.query(User).filter(User.id == uid).first()
    if not user or not user.is_active or user.company_id != cid:
        return None
    access, refresh, resolved = create_tenant_token_pair(user, db, site_id=site_id)
    return access, refresh, user, resolved
