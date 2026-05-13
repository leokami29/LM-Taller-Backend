from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.enums import UserRole
from app.core.permissions import PLATFORM_COMPANIES_READ, PLATFORM_COMPANIES_WRITE
from app.core.security import SecurityUtils
from app.dependencies import RequirePlatformPermission
from app.db.models.company import Company
from app.db.models.platform_user import PlatformUser
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.platform import PlatformCompanyCreate, PlatformCompanyResponse, PlatformCompanyUpdate

router = APIRouter(prefix="/companies", tags=["platform-companies"])


@router.get("/", response_model=List[PlatformCompanyResponse])
def list_companies(
    db: Session = Depends(get_db),
    _user: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_READ)),
) -> List[Company]:
    return db.query(Company).order_by(Company.created_at.desc()).all()


@router.get("/{company_id}", response_model=PlatformCompanyResponse)
def get_company(
    company_id: UUID,
    db: Session = Depends(get_db),
    _user: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_READ)),
) -> Company:
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return c


@router.patch("/{company_id}", response_model=PlatformCompanyResponse)
def patch_company(
    company_id: UUID,
    payload: PlatformCompanyUpdate,
    db: Session = Depends(get_db),
    _user: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_WRITE)),
) -> Company:
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(c, k, v)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.post("/", response_model=PlatformCompanyResponse, status_code=status.HTTP_201_CREATED)
def create_company_with_admin(
    payload: PlatformCompanyCreate,
    db: Session = Depends(get_db),
    _user: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_WRITE)),
) -> Company:
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
    return company
