from typing import List
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.core.dt import utc_now
from app.core.enums import SubscriptionStatus, UserRole
from app.core.permissions import PLATFORM_COMPANIES_READ, PLATFORM_COMPANIES_WRITE
from app.core.security import SecurityUtils
from app.db.catalog.models import Plan, Subscription, TenantRouting
from app.db.models.company import Company
from app.db.models.platform_user import PlatformUser
from app.db.models.rbac import Site
from app.db.models.user import User
from app.db.session import get_db, tenant_engine_manager
from app.dependencies import RequirePlatformPermission
from app.schemas.platform import (
    PlatformCompanyCreate,
    PlatformCompanyResponse,
    PlatformCompanyUpdate,
    PlatformSiteResponse,
)
from app.services.permission_service import get_catalog_subscription_period_end
from app.services.tenant_config_events import TenantConfigReason, company_patch_meta, post_company_mutation

router = APIRouter(prefix="/companies", tags=["platform-companies"])


def _emit_company_patch(c: Company, changed: dict) -> None:
    period_end = get_catalog_subscription_period_end(c.id)
    meta = company_patch_meta(c, current_period_end=period_end)
    sub_keys = {"plan", "subscription_status", "active_users_limit", "billing_email"}
    reason = (
        TenantConfigReason.SUBSCRIPTION
        if sub_keys & set(changed.keys())
        else TenantConfigReason.COMPANY_STATUS
    )
    post_company_mutation(c.id, reason, meta=meta)


def _tenant_company_to_response(c: Company) -> PlatformCompanyResponse:
    return PlatformCompanyResponse(
        id=c.id,
        name=c.name,
        nit_rut=c.nit_rut,
        address=c.address,
        phone=c.phone,
        email=c.email,
        country=c.country,
        currency=c.currency,
        is_active=c.is_active,
        created_at=c.created_at,
        plan_code=c.plan.value,
        subscription_status=c.subscription_status,
        subscription_billing_email=c.billing_email,
    )


def _routing_row_to_response(
    row: TenantRouting,
    *,
    plan_code: str | None = None,
    subscription_status: SubscriptionStatus | None = None,
    subscription_billing_email: str | None = None,
) -> PlatformCompanyResponse:
    return PlatformCompanyResponse(
        id=row.company_id,
        name=row.display_name or row.slug,
        nit_rut=row.nit_rut or "",
        address=row.address or "",
        phone=row.phone,
        email=row.email,
        country=row.country or "Colombia",
        currency=row.currency or "COP",
        is_active=row.is_active,
        created_at=row.company_created_at or utc_now(),
        plan_code=plan_code,
        subscription_status=subscription_status,
        subscription_billing_email=subscription_billing_email,
    )


@router.get("/", response_model=List[PlatformCompanyResponse])
def list_companies(
    db: Session = Depends(get_db),
    _user: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_READ)),
) -> List[PlatformCompanyResponse]:
    if settings.USE_TENANT_DATABASE_ROUTING:
        fetched = (
            db.query(TenantRouting, Plan.code, Subscription.status, Subscription.billing_email)
            .outerjoin(Subscription, Subscription.company_id == TenantRouting.company_id)
            .outerjoin(Plan, Plan.id == Subscription.plan_id)
            .order_by(TenantRouting.company_created_at.desc().nulls_last(), TenantRouting.slug)
            .all()
        )
        return [
            _routing_row_to_response(
                r,
                plan_code=pcode,
                subscription_status=st,
                subscription_billing_email=b_email,
            )
            for r, pcode, st, b_email in fetched
        ]
    companies = db.query(Company).order_by(Company.created_at.desc()).all()
    return [_tenant_company_to_response(c) for c in companies]


@router.get("/{company_id}", response_model=PlatformCompanyResponse)
def get_company(
    company_id: UUID,
    db: Session = Depends(get_db),
    _user: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_READ)),
) -> PlatformCompanyResponse:
    if settings.USE_TENANT_DATABASE_ROUTING:
        row = db.query(TenantRouting).filter(TenantRouting.company_id == company_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Empresa no encontrada")
        eng = tenant_engine_manager.get_engine(row.database_url)
        TenantSession = sessionmaker(autocommit=False, autoflush=False, bind=eng, class_=Session)
        tdb = TenantSession()
        try:
            c = tdb.query(Company).filter(Company.id == company_id).first()
            if not c:
                raise HTTPException(status_code=404, detail="Empresa no encontrada en data plane")
            return _tenant_company_to_response(c)
        finally:
            tdb.close()
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return _tenant_company_to_response(c)


@router.patch("/{company_id}", response_model=PlatformCompanyResponse)
def patch_company(
    company_id: UUID,
    payload: PlatformCompanyUpdate,
    db: Session = Depends(get_db),
    _user: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_WRITE)),
) -> PlatformCompanyResponse:
    if settings.USE_TENANT_DATABASE_ROUTING:
        row = db.query(TenantRouting).filter(TenantRouting.company_id == company_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Empresa no encontrada")
        eng = tenant_engine_manager.get_engine(row.database_url)
        TenantSession = sessionmaker(autocommit=False, autoflush=False, bind=eng, class_=Session)
        tdb = TenantSession()
        try:
            c = tdb.query(Company).filter(Company.id == company_id).first()
            if not c:
                raise HTTPException(status_code=404, detail="Empresa no encontrada en data plane")
            data = payload.model_dump(exclude_unset=True)
            for k, v in data.items():
                setattr(c, k, v)
            tdb.add(c)
            tdb.commit()
            tdb.refresh(c)
            row.display_name = c.name
            row.nit_rut = c.nit_rut
            row.address = c.address
            row.phone = c.phone
            row.email = c.email
            row.country = c.country
            row.currency = c.currency
            row.is_active = c.is_active
            db.add(row)
            db.commit()
            db.refresh(row)
            _emit_company_patch(c, data)
            return _tenant_company_to_response(c)
        finally:
            tdb.close()
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(c, k, v)
    db.add(c)
    db.commit()
    db.refresh(c)
    _emit_company_patch(c, data)
    return _tenant_company_to_response(c)


@router.post("/", response_model=PlatformCompanyResponse, status_code=status.HTTP_201_CREATED)
def create_company_with_admin(
    payload: PlatformCompanyCreate,
    db: Session = Depends(get_db),
    _user: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_WRITE)),
) -> PlatformCompanyResponse:
    if settings.USE_TENANT_DATABASE_ROUTING:
        if not payload.tenant_slug or not payload.tenant_slug.strip():
            raise HTTPException(status_code=400, detail="tenant_slug es obligatorio")
        if not payload.tenant_database_url or not payload.tenant_database_url.strip():
            raise HTTPException(status_code=400, detail="tenant_database_url es obligatorio")
        slug_key = payload.tenant_slug.strip().lower()
        exists_slug = (
            db.query(TenantRouting).filter(func.lower(TenantRouting.slug) == slug_key).first()
        )
        if exists_slug:
            raise HTTPException(status_code=400, detail="Slug de taller ya registrado")

        company_id = uuid4()
        eng = tenant_engine_manager.get_engine(payload.tenant_database_url.strip())
        TenantSession = sessionmaker(autocommit=False, autoflush=False, bind=eng, class_=Session)
        tdb = TenantSession()
        try:
            exists_nit = tdb.query(Company).filter(Company.nit_rut == payload.nit_rut).first()
            if exists_nit:
                raise HTTPException(status_code=400, detail="NIT/RUT ya registrado en la base del taller")
            if payload.email:
                exists_email = tdb.query(Company).filter(Company.email == str(payload.email)).first()
                if exists_email:
                    raise HTTPException(status_code=400, detail="Email de empresa ya registrado en la base del taller")

            company = Company(
                id=company_id,
                name=payload.name,
                nit_rut=payload.nit_rut,
                address=payload.address,
                phone=payload.phone,
                email=str(payload.email) if payload.email else None,
                country=payload.country,
                currency=payload.currency,
            )
            tdb.add(company)
            tdb.flush()

            admin = User(
                company_id=company.id,
                email=str(payload.admin_email),
                full_name=payload.admin_full_name,
                hashed_password=SecurityUtils.hash_password(payload.admin_password),
                role=UserRole.ADMIN,
            )
            tdb.add(admin)
            tdb.commit()
            tdb.refresh(company)
        except HTTPException:
            tdb.rollback()
            raise
        except Exception:
            tdb.rollback()
            raise
        finally:
            tdb.close()

        now = utc_now()
        row = TenantRouting(
            company_id=company_id,
            slug=payload.tenant_slug.strip(),
            database_url=payload.tenant_database_url.strip(),
            is_active=True,
            display_name=payload.name,
            nit_rut=payload.nit_rut,
            address=payload.address,
            phone=payload.phone,
            email=str(payload.email) if payload.email else None,
            country=payload.country,
            currency=payload.currency,
            company_created_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _routing_row_to_response(row)

    exists_nit = db.query(Company).filter(Company.nit_rut == payload.nit_rut).first()
    if exists_nit:
        raise HTTPException(status_code=400, detail="NIT/RUT ya registrado")
    if payload.email:
        exists_email = db.query(Company).filter(Company.email == str(payload.email)).first()
        if exists_email:
            raise HTTPException(status_code=400, detail="Email de empresa ya registrado")

    company = Company(
        name=payload.name,
        nit_rut=payload.nit_rut,
        address=payload.address,
        phone=payload.phone,
        email=str(payload.email) if payload.email else None,
        country=payload.country,
        currency=payload.currency,
    )
    db.add(company)
    db.flush()

    admin = User(
        company_id=company.id,
        email=str(payload.admin_email),
        full_name=payload.admin_full_name,
        hashed_password=SecurityUtils.hash_password(payload.admin_password),
        role=UserRole.ADMIN,
    )
    db.add(admin)
    db.commit()
    db.refresh(company)
    return _tenant_company_to_response(company)


@router.get("/{company_id}/sites", response_model=List[PlatformSiteResponse])
def get_company_sites(
    company_id: UUID,
    db: Session = Depends(get_db),
    _user: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_READ)),
) -> List[PlatformSiteResponse]:
    if settings.USE_TENANT_DATABASE_ROUTING:
        row = db.query(TenantRouting).filter(TenantRouting.company_id == company_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Empresa no encontrada")
        eng = tenant_engine_manager.get_engine(row.database_url)
        TenantSession = sessionmaker(autocommit=False, autoflush=False, bind=eng, class_=Session)
        tdb = TenantSession()
        try:
            sites = tdb.query(Site).filter(Site.company_id == company_id).all()
            return sites
        finally:
            tdb.close()
    
    sites = db.query(Site).filter(Site.company_id == company_id).all()
    return sites


@router.get("/sites/global")
def get_all_global_sites(
    db: Session = Depends(get_db),
    _user: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_READ)),
):
    results = []
    if settings.USE_TENANT_DATABASE_ROUTING:
        routings = db.query(TenantRouting).filter(TenantRouting.is_active == True).all()
        for row in routings:
            try:
                eng = tenant_engine_manager.get_engine(row.database_url)
                TenantSession = sessionmaker(autocommit=False, autoflush=False, bind=eng, class_=Session)
                tdb = TenantSession()
                try:
                    sites = tdb.query(Site).filter(Site.company_id == row.company_id).all()
                    for s in sites:
                        results.append({
                            "id": s.id,
                            "company_id": row.company_id,
                            "company_name": row.display_name or row.slug,
                            "name": s.name,
                            "location": s.location,
                            "is_active": s.is_active,
                            "created_at": s.created_at
                        })
                finally:
                    tdb.close()
            except Exception:
                pass
        return results

    # If mono-db
    sites = db.query(Site).all()
    companies = {c.id: c.name for c in db.query(Company).all()}
    for s in sites:
        results.append({
            "id": s.id,
            "company_id": s.company_id,
            "company_name": companies.get(s.company_id, "Unknown"),
            "name": s.name,
            "location": s.location,
            "is_active": s.is_active,
            "created_at": s.created_at
        })
    return results
