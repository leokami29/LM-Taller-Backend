"""Admin taller: políticas de sesión (misma lógica que plataforma, scope RLS)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.platform.v1.endpoints.session_policy import build_policy_document
from app.core.permissions import ADMIN_USERS
from app.db.models.company import Company
from app.db.models.rbac import Site
from app.db.models.user import User
from app.db.session import get_db
from app.dependencies import RequirePermission
from app.schemas.session_policy import (
    CompanySessionPolicyUpdate,
    SessionPolicyDocumentResponse,
    SiteSessionPolicyUpdate,
    UserSessionPolicyUpdate,
)
from app.services.session_policy_service import (
    normalize_entry,
    remove_site_policy,
    remove_user_policy,
    set_company_policy,
    set_site_policy,
    set_user_policy,
)
from app.services.tenant_config_events import (
    TenantConfigReason,
    bump_company_config_revision,
    notify_company_config_changed,
)

router = APIRouter(prefix="/admin/session-policy", tags=["admin-session-policy"])


def _company_or_404(db: Session, admin: User) -> Company:
    company = db.query(Company).filter(Company.id == admin.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return company


def _document(db: Session, company: Company) -> SessionPolicyDocumentResponse:
    sites = db.query(Site).filter(Site.company_id == company.id).order_by(Site.name).all()
    users = db.query(User).filter(User.company_id == company.id).order_by(User.full_name).all()
    return build_policy_document(company, sites, users)


@router.get("", response_model=SessionPolicyDocumentResponse)
def get_session_policy(
    db: Session = Depends(get_db),
    admin: User = Depends(RequirePermission(ADMIN_USERS)),
) -> SessionPolicyDocumentResponse:
    company = _company_or_404(db, admin)
    return _document(db, company)


@router.put("", response_model=SessionPolicyDocumentResponse)
def update_company_session_policy(
    payload: CompanySessionPolicyUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(RequirePermission(ADMIN_USERS)),
) -> SessionPolicyDocumentResponse:
    company = _company_or_404(db, admin)
    entry = normalize_entry(payload.entry.model_dump())
    set_company_policy(
        company,
        entry if entry.mode == "explicit" else None,
        apply_to_all_sites=payload.apply_to_all_sites,
    )
    revision = bump_company_config_revision(company)
    db.add(company)
    db.commit()
    notify_company_config_changed(company.id, TenantConfigReason.SESSION_POLICY, revision)
    db.refresh(company)
    return _document(db, company)


@router.put("/sites/{site_id}", response_model=SessionPolicyDocumentResponse)
def update_site_session_policy(
    site_id: UUID,
    payload: SiteSessionPolicyUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(RequirePermission(ADMIN_USERS)),
) -> SessionPolicyDocumentResponse:
    company = _company_or_404(db, admin)
    site = db.query(Site).filter(Site.id == site_id, Site.company_id == company.id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Sede no encontrada")
    entry = normalize_entry(payload.entry.model_dump())
    set_site_policy(company, site_id, entry)
    revision = bump_company_config_revision(company)
    db.add(company)
    db.commit()
    notify_company_config_changed(company.id, TenantConfigReason.SESSION_POLICY, revision)
    db.refresh(company)
    return _document(db, company)


@router.delete("/sites/{site_id}", response_model=SessionPolicyDocumentResponse)
def delete_site_session_policy(
    site_id: UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(RequirePermission(ADMIN_USERS)),
) -> SessionPolicyDocumentResponse:
    company = _company_or_404(db, admin)
    remove_site_policy(company, site_id)
    revision = bump_company_config_revision(company)
    db.add(company)
    db.commit()
    notify_company_config_changed(company.id, TenantConfigReason.SESSION_POLICY, revision)
    db.refresh(company)
    return _document(db, company)


@router.put("/users/{user_id}", response_model=SessionPolicyDocumentResponse)
def update_user_session_policy(
    user_id: UUID,
    payload: UserSessionPolicyUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(RequirePermission(ADMIN_USERS)),
) -> SessionPolicyDocumentResponse:
    company = _company_or_404(db, admin)
    user = db.query(User).filter(User.id == user_id, User.company_id == company.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    entry = normalize_entry(payload.entry.model_dump())
    set_user_policy(company, user_id, entry)
    revision = bump_company_config_revision(company)
    db.add(company)
    db.commit()
    notify_company_config_changed(company.id, TenantConfigReason.SESSION_POLICY, revision)
    db.refresh(company)
    return _document(db, company)


@router.delete("/users/{user_id}", response_model=SessionPolicyDocumentResponse)
def delete_user_session_policy(
    user_id: UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(RequirePermission(ADMIN_USERS)),
) -> SessionPolicyDocumentResponse:
    company = _company_or_404(db, admin)
    remove_user_policy(company, user_id)
    revision = bump_company_config_revision(company)
    db.add(company)
    db.commit()
    notify_company_config_changed(company.id, TenantConfigReason.SESSION_POLICY, revision)
    db.refresh(company)
    return _document(db, company)
