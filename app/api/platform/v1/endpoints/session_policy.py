"""API plataforma: políticas de sesión por empresa / sede / usuario."""

from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.core.permissions import PLATFORM_COMPANIES_READ, PLATFORM_COMPANIES_WRITE
from app.dependencies import RequirePlatformPermission
from app.db.catalog.models import TenantRouting
from app.db.models.company import Company
from app.db.models.rbac import Site
from app.db.models.user import User
from app.db.session import get_db, tenant_engine_manager
from app.schemas.session_policy import (
    CompanySessionPolicyUpdate,
    GlobalSessionDefaultsSchema,
    PlatformCompanyUserSummary,
    SessionEffectiveSchema,
    SessionPolicyDocumentResponse,
    SessionPolicyEntrySchema,
    SessionPolicyScopeEffective,
    SiteSessionPolicyUpdate,
    UserSessionPolicyUpdate,
)
from app.services.session_policy_service import (
    SessionPolicyEntry,
    entry_display,
    get_policies,
    normalize_entry,
    remove_site_policy,
    remove_user_policy,
    resolve_tenant_session,
    set_company_policy,
    set_site_policy,
    set_user_policy,
)
from app.services import platform_config_service as pcfg

router = APIRouter(prefix="/companies", tags=["platform-session-policy"])


def _global_defaults_schema():
    s = pcfg.get_session_settings()
    return {
        "access_token_minutes": s.tenant_access_token_minutes,
        "refresh_token_days": s.tenant_refresh_token_days,
    }


def _entry_schema(entry: SessionPolicyEntry | None) -> SessionPolicyEntrySchema:
    d = entry_display(entry)
    return SessionPolicyEntrySchema(**d)


def _effective_schema(company: Company, *, user_id: UUID, site_id: UUID | None = None) -> SessionEffectiveSchema:
    r = resolve_tenant_session(company, user_id=user_id, site_id=site_id)
    return SessionEffectiveSchema(
        access_token_minutes=r.access_token_minutes,
        refresh_token_days=r.refresh_token_days,
        source=r.source,
    )


def build_policy_document(
    company: Company,
    sites: list[Site],
    users: list[User],
) -> SessionPolicyDocumentResponse:
    doc = get_policies(company)
    company_entry = doc.company or SessionPolicyEntry(mode="inherit")
    dummy_uid = users[0].id if users else UUID(int=0)
    company_effective = _effective_schema(company, user_id=dummy_uid)
    site_rows: list[SessionPolicyScopeEffective] = []
    for s in sites:
        site_entry = doc.sites.get(str(s.id), SessionPolicyEntry(mode="inherit"))
        site_rows.append(
            SessionPolicyScopeEffective(
                id=s.id,
                entry=_entry_schema(site_entry),
                effective=_effective_schema(company, user_id=dummy_uid, site_id=s.id),
            )
        )
    user_rows: list[SessionPolicyScopeEffective] = []
    for u in users:
        user_entry = doc.users.get(str(u.id), SessionPolicyEntry(mode="inherit"))
        user_rows.append(
            SessionPolicyScopeEffective(
                id=u.id,
                entry=_entry_schema(user_entry),
                effective=_effective_schema(company, user_id=u.id),
            )
        )
    g = GlobalSessionDefaultsSchema(**_global_defaults_schema())
    return SessionPolicyDocumentResponse(
        global_defaults=g,
        company=_entry_schema(company_entry),
        company_effective=company_effective,
        sites=site_rows,
        users=user_rows,
    )


def _with_tenant_company(company_id: UUID, catalog_db: Session, fn):
    if settings.USE_TENANT_DATABASE_ROUTING:
        row = catalog_db.query(TenantRouting).filter(TenantRouting.company_id == company_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Empresa no encontrada")
        eng = tenant_engine_manager.get_engine(row.database_url)
        TenantSession = sessionmaker(autocommit=False, autoflush=False, bind=eng, class_=Session)
        tdb = TenantSession()
        try:
            company = tdb.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail="Empresa no encontrada en tenant")
            return fn(tdb, company)
        finally:
            tdb.close()

    company = catalog_db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return fn(catalog_db, company)


@router.get("/{company_id}/session-policy", response_model=SessionPolicyDocumentResponse)
def get_company_session_policy(
    company_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(RequirePlatformPermission(PLATFORM_COMPANIES_READ)),
):
    def _read(tdb: Session, company: Company):
        sites = tdb.query(Site).filter(Site.company_id == company_id).order_by(Site.name).all()
        users = tdb.query(User).filter(User.company_id == company_id).order_by(User.full_name).all()
        return build_policy_document(company, sites, users)

    return _with_tenant_company(company_id, db, _read)


@router.put("/{company_id}/session-policy", response_model=SessionPolicyDocumentResponse)
def update_company_session_policy(
    company_id: UUID,
    payload: CompanySessionPolicyUpdate,
    db: Session = Depends(get_db),
    _user=Depends(RequirePlatformPermission(PLATFORM_COMPANIES_WRITE)),
):
    def _write(tdb: Session, company: Company):
        entry = normalize_entry(payload.entry.model_dump())
        set_company_policy(company, entry if entry.mode == "explicit" else None, apply_to_all_sites=payload.apply_to_all_sites)
        tdb.add(company)
        tdb.commit()
        tdb.refresh(company)
        sites = tdb.query(Site).filter(Site.company_id == company_id).order_by(Site.name).all()
        users = tdb.query(User).filter(User.company_id == company_id).order_by(User.full_name).all()
        return build_policy_document(company, sites, users)

    return _with_tenant_company(company_id, db, _write)


@router.put("/{company_id}/session-policy/sites/{site_id}", response_model=SessionPolicyDocumentResponse)
def update_site_session_policy(
    company_id: UUID,
    site_id: UUID,
    payload: SiteSessionPolicyUpdate,
    db: Session = Depends(get_db),
    _user=Depends(RequirePlatformPermission(PLATFORM_COMPANIES_WRITE)),
):
    def _write(tdb: Session, company: Company):
        site = tdb.query(Site).filter(Site.id == site_id, Site.company_id == company_id).first()
        if not site:
            raise HTTPException(status_code=404, detail="Sede no encontrada")
        entry = normalize_entry(payload.entry.model_dump())
        set_site_policy(company, site_id, entry)
        tdb.add(company)
        tdb.commit()
        tdb.refresh(company)
        sites = tdb.query(Site).filter(Site.company_id == company_id).order_by(Site.name).all()
        users = tdb.query(User).filter(User.company_id == company_id).order_by(User.full_name).all()
        return build_policy_document(company, sites, users)

    return _with_tenant_company(company_id, db, _write)


@router.delete("/{company_id}/session-policy/sites/{site_id}", response_model=SessionPolicyDocumentResponse)
def delete_site_session_policy(
    company_id: UUID,
    site_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(RequirePlatformPermission(PLATFORM_COMPANIES_WRITE)),
):
    def _write(tdb: Session, company: Company):
        remove_site_policy(company, site_id)
        tdb.add(company)
        tdb.commit()
        tdb.refresh(company)
        sites = tdb.query(Site).filter(Site.company_id == company_id).order_by(Site.name).all()
        users = tdb.query(User).filter(User.company_id == company_id).order_by(User.full_name).all()
        return build_policy_document(company, sites, users)

    return _with_tenant_company(company_id, db, _write)


@router.put("/{company_id}/session-policy/users/{user_id}", response_model=SessionPolicyDocumentResponse)
def update_user_session_policy(
    company_id: UUID,
    user_id: UUID,
    payload: UserSessionPolicyUpdate,
    db: Session = Depends(get_db),
    _user=Depends(RequirePlatformPermission(PLATFORM_COMPANIES_WRITE)),
):
    def _write(tdb: Session, company: Company):
        user = tdb.query(User).filter(User.id == user_id, User.company_id == company_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        entry = normalize_entry(payload.entry.model_dump())
        set_user_policy(company, user_id, entry)
        tdb.add(company)
        tdb.commit()
        tdb.refresh(company)
        sites = tdb.query(Site).filter(Site.company_id == company_id).order_by(Site.name).all()
        users = tdb.query(User).filter(User.company_id == company_id).order_by(User.full_name).all()
        return build_policy_document(company, sites, users)

    return _with_tenant_company(company_id, db, _write)


@router.delete("/{company_id}/session-policy/users/{user_id}", response_model=SessionPolicyDocumentResponse)
def delete_user_session_policy(
    company_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(RequirePlatformPermission(PLATFORM_COMPANIES_WRITE)),
):
    def _write(tdb: Session, company: Company):
        remove_user_policy(company, user_id)
        tdb.add(company)
        tdb.commit()
        tdb.refresh(company)
        sites = tdb.query(Site).filter(Site.company_id == company_id).order_by(Site.name).all()
        users = tdb.query(User).filter(User.company_id == company_id).order_by(User.full_name).all()
        return build_policy_document(company, sites, users)

    return _with_tenant_company(company_id, db, _write)


@router.get("/{company_id}/users", response_model=List[PlatformCompanyUserSummary])
def list_company_users(
    company_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(RequirePlatformPermission(PLATFORM_COMPANIES_READ)),
):
    def _read(tdb: Session, company: Company):
        rows = tdb.query(User).filter(User.company_id == company.id).order_by(User.full_name).all()
        return [
            PlatformCompanyUserSummary(
                id=u.id,
                email=u.email,
                full_name=u.full_name,
                is_active=u.is_active,
            )
            for u in rows
        ]

    return _with_tenant_company(company_id, db, _read)
