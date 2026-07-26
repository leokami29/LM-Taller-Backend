from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.enums import UserRole
from app.core.network_guards import validate_logo_reference, validate_smtp_endpoint
from app.core.permissions import ADMIN_USERS
from app.core.security import SecurityUtils
from app.db.models.company import Company
from app.db.models.rbac import Site, UserSiteRole
from app.db.models.user import User
from app.db.session import get_db
from app.dependencies import PermissionContext, RequirePermission, get_permission_context
from app.schemas.company import CompanyEmailSettings, CompanyLogoUpdate, CompanyResponse, CompanyUpdate
from app.schemas.user import UserAdminCreate, UserPasswordUpdate, UserResponse, UserUpdate
from app.services.permission_service import PermissionService
from app.services.tenant_config_events import (
    TenantConfigReason,
    bump_company_config_revision,
    notify_company_config_changed,
)
from app.utils.helpers import apply_allowed_updates

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
    apply_allowed_updates(user, data, ("full_name", "phone", "is_active"))
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
    ctx: PermissionContext = Depends(get_permission_context),
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

    PermissionService(db).log_action(
        user_id=ctx.user_id,
        company_id=ctx.company_id,
        action="user_password_reset",
        resource="user",
        resource_id=user.id,
        request=None,
        site_id=ctx.site_id,
    )
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
    if "logo_url" in data:
        try:
            data["logo_url"] = validate_logo_reference(data["logo_url"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    apply_allowed_updates(company, data, ("name", "address", "phone", "email", "country", "currency", "logo_url"))
        
    revision = bump_company_config_revision(company)
    db.add(company)
    db.commit()
    notify_company_config_changed(company.id, TenantConfigReason.COMPANY_STATUS, revision)
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


@router.patch("/company/logo", response_model=CompanyResponse)
def update_company_logo(
    payload: CompanyLogoUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(RequirePermission(ADMIN_USERS)),
    ctx: PermissionContext = Depends(get_permission_context),
) -> Company:
    company = db.query(Company).filter(Company.id == admin.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    try:
        if payload.logo_base64 and payload.mime_type:
            data_uri = f"data:{payload.mime_type};base64,{payload.logo_base64}"
            company.logo_url = validate_logo_reference(data_uri)
        elif payload.logo_url is not None:
            company.logo_url = validate_logo_reference(payload.logo_url)
        else:
            raise HTTPException(status_code=400, detail="Debe proveer logo_url o logo_base64+mime_type")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    revision = bump_company_config_revision(company)
    db.add(company)
    db.commit()
    notify_company_config_changed(company.id, TenantConfigReason.COMPANY_STATUS, revision)
    db.refresh(company)
    return company


@router.get("/company/email-settings", response_model=CompanyEmailSettings)
def get_company_email_settings(
    db: Session = Depends(get_db),
    admin: User = Depends(RequirePermission(ADMIN_USERS)),
) -> CompanyEmailSettings:
    company = db.query(Company).filter(Company.id == admin.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    raw = dict((company.settings_json or {}).get("email_settings", {}) or {})
    if raw.get("smtp_password"):
        raw["smtp_password"] = None
    return CompanyEmailSettings(**raw)


@router.patch("/company/email-settings", response_model=CompanyEmailSettings)
def update_company_email_settings(
    payload: CompanyEmailSettings,
    db: Session = Depends(get_db),
    admin: User = Depends(RequirePermission(ADMIN_USERS)),
    ctx: PermissionContext = Depends(get_permission_context),
) -> CompanyEmailSettings:
    company = db.query(Company).filter(Company.id == admin.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    try:
        host, port = validate_smtp_endpoint(payload.smtp_host, payload.smtp_port)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    settings = dict(company.settings_json or {})
    email_data = payload.model_dump(exclude_none=True)
    if host is not None:
        email_data["smtp_host"] = host
    email_data["smtp_port"] = port
    # Si no envían password, conservar el existente.
    if not email_data.get("smtp_password"):
        prev = (company.settings_json or {}).get("email_settings") or {}
        if prev.get("smtp_password"):
            email_data["smtp_password"] = prev["smtp_password"]
    settings["email_settings"] = email_data
    company.settings_json = settings
    db.add(company)
    db.commit()
    PermissionService(db).log_action(
        user_id=ctx.user_id,
        company_id=ctx.company_id,
        action="updated_email_settings",
        resource="company",
        resource_id=company.id,
        request=None,
        site_id=ctx.site_id,
        changes={"smtp_host": host},
    )
    safe = dict(email_data)
    safe["smtp_password"] = None
    return CompanyEmailSettings(**safe)
