from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.enums import UserRole
from app.core.permissions import ADMIN_USERS
from app.core.security import SecurityUtils
from app.dependencies import PermissionContext, RequirePermission, get_permission_context
from app.db.models.rbac import Site, UserSiteRole
from app.db.models.user import User
from app.db.models.company import Company
from app.db.session import get_db
from app.schemas.user import UserAdminCreate, UserPasswordUpdate, UserResponse, UserUpdate
from app.schemas.company import CompanyResponse, CompanyUpdate
from app.services.permission_service import PermissionService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=List[UserResponse])
def list_company_users(
    db: Session = Depends(get_db),
    admin: User = Depends(RequirePermission(ADMIN_USERS)),
) -> List[User]:
    return db.query(User).filter(User.company_id == admin.company_id).order_by(User.created_at.desc()).all()


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_company_user(
    payload: UserAdminCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(RequirePermission(ADMIN_USERS)),
    ctx: PermissionContext = Depends(get_permission_context),
) -> User:
    svc = PermissionService(db)
    ok, reason = svc.can_add_user(admin.company_id)
    if not ok:
        raise HTTPException(status_code=403, detail=reason)

    exists = (
        db.query(User)
        .filter(User.company_id == admin.company_id, User.email == str(payload.email))
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="El email ya está registrado en la empresa")

    user = User(
        company_id=admin.company_id,
        email=str(payload.email),
        full_name=payload.full_name,
        hashed_password=SecurityUtils.hash_password(payload.password),
        role=payload.role,
        phone=payload.phone,
        created_by_id=admin.id,
    )
    db.add(user)
    db.flush()

    site_roles = payload.site_roles
    if not site_roles:
        principal = (
            db.query(Site)
            .filter(Site.company_id == admin.company_id, Site.name == "Principal")
            .first()
        )
        site_id = principal.id if principal and payload.role != UserRole.ADMIN else None
        db.add(
            UserSiteRole(
                user_id=user.id,
                company_id=admin.company_id,
                site_id=site_id,
                role=payload.role,
            )
        )
    else:
        for sr in site_roles:
            db.add(
                UserSiteRole(
                    user_id=user.id,
                    company_id=admin.company_id,
                    site_id=sr.site_id,
                    role=sr.role,
                )
            )

    db.commit()
    db.refresh(user)
    svc.log_action(
        user_id=ctx.user_id,
        company_id=ctx.company_id,
        action="created_user",
        resource="user",
        resource_id=user.id,
        changes={"email": user.email, "role": payload.role.value},
        request=request,
        site_id=ctx.site_id,
    )
    return user


@router.patch("/users/{user_id}/deactivate", response_model=UserResponse)
def deactivate_company_user(
    user_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    ctx: PermissionContext = Depends(get_permission_context),
    _: User = Depends(RequirePermission(ADMIN_USERS)),
) -> User:
    user = (
        db.query(User)
        .filter(User.id == user_id, User.company_id == ctx.company_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    user.is_active = False
    db.commit()
    db.refresh(user)
    PermissionService(db).log_action(
        user_id=ctx.user_id,
        company_id=ctx.company_id,
        action="user_deactivated",
        resource="user",
        resource_id=user.id,
        request=request,
        site_id=ctx.site_id,
    )
    return user


@router.put("/users/{user_id}", response_model=UserResponse)
def update_company_user(
    user_id: UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(RequirePermission(ADMIN_USERS)),
) -> User:
    user = (
        db.query(User)
        .filter(User.id == user_id, User.company_id == admin.company_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    data = payload.model_dump(exclude_unset=True)
    if "role" in data:
        raise HTTPException(
            status_code=400,
            detail="Use el flujo de solicitud de cambio de rol para modificar el rol",
        )
    for k, v in data.items():
        setattr(user, k, v)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}/password", response_model=UserResponse)
def reset_user_password(
    user_id: UUID,
    payload: UserPasswordUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(RequirePermission(ADMIN_USERS)),
) -> User:
    user = (
        db.query(User)
        .filter(User.id == user_id, User.company_id == admin.company_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    user.hashed_password = SecurityUtils.hash_password(payload.password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/company", response_model=CompanyResponse)
def update_own_company(
    payload: CompanyUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(RequirePermission(ADMIN_USERS)),
    ctx: PermissionContext = Depends(get_permission_context),
) -> Company:
    company = db.query(Company).filter(Company.id == admin.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return company

    for k, v in data.items():
        setattr(company, k, v)
        
    db.add(company)
    db.commit()
    db.refresh(company)
    
    PermissionService(db).log_action(
        user_id=ctx.user_id,
        company_id=ctx.company_id,
        action="updated_company_profile",
        resource="company",
        resource_id=company.id,
        request=None,
        site_id=ctx.site_id,
        changes=data,
    )
    return company

@router.get("/company", response_model=CompanyResponse)
def get_own_company(
    db: Session = Depends(get_db),
    admin: User = Depends(RequirePermission(ADMIN_USERS)),
) -> Company:
    company = db.query(Company).filter(Company.id == admin.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return company
