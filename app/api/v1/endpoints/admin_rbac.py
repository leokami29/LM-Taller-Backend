"""Admin: sedes, workflow de roles, permisos temporales y auditoría."""

from __future__ import annotations

from datetime import timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.dt import utc_now
from app.core.enums import RoleChangeStatus, UserRole
from app.core.permissions import ADMIN_USERS
from app.dependencies import PermissionContext, RequirePermission, get_permission_context
from app.db.models.rbac import RoleChangeRequest, Site, TemporaryPermission, UserSiteRole
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.rbac import (
    AuditLogResponse,
    RoleChangeRequestCreate,
    RoleChangeRequestResponse,
    SiteCreate,
    SiteResponse,
    SiteUpdate,
    TemporaryPermissionGrant,
    TemporaryPermissionResponse,
    UserSiteRoleInput,
    UserWithRolesResponse,
)
from app.services.permission_service import PermissionService

router = APIRouter(prefix="/admin", tags=["admin-rbac"])


def _user_with_roles(db: Session, user: User) -> UserWithRolesResponse:
    roles = (
        db.query(UserSiteRole)
        .filter(UserSiteRole.user_id == user.id, UserSiteRole.company_id == user.company_id)
        .all()
    )
    from app.schemas.rbac import UserSiteRoleResponse

    return UserWithRolesResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        role=user.role,
        site_roles=[UserSiteRoleResponse.model_validate(r) for r in roles],
    )


@router.get("/sites", response_model=List[SiteResponse])
def list_sites(
    db: Session = Depends(get_db),
    _: User = Depends(RequirePermission(ADMIN_USERS)),
    ctx: PermissionContext = Depends(get_permission_context),
) -> List[Site]:
    return (
        db.query(Site)
        .filter(Site.company_id == ctx.company_id)
        .order_by(Site.name)
        .all()
    )


@router.post("/sites", response_model=SiteResponse, status_code=status.HTTP_201_CREATED)
def create_site(
    payload: SiteCreate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: PermissionContext = Depends(get_permission_context),
    _: User = Depends(RequirePermission(ADMIN_USERS)),
) -> Site:
    site = Site(company_id=ctx.company_id, name=payload.name, location=payload.location)
    db.add(site)
    db.commit()
    db.refresh(site)
    PermissionService(db).log_action(
        user_id=ctx.user_id,
        company_id=ctx.company_id,
        action="created_site",
        resource="site",
        resource_id=site.id,
        changes={"name": payload.name},
        request=request,
        site_id=ctx.site_id,
    )
    return site


@router.put("/sites/{site_id}", response_model=SiteResponse)
def update_site(
    site_id: UUID,
    payload: SiteUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(RequirePermission(ADMIN_USERS)),
    ctx: PermissionContext = Depends(get_permission_context),
) -> Site:
    site = db.query(Site).filter(Site.id == site_id, Site.company_id == ctx.company_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Sede no encontrada")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(site, k, v)
    db.commit()
    db.refresh(site)
    return site


@router.get("/users/detailed", response_model=List[UserWithRolesResponse])
def list_users_detailed(
    site_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(RequirePermission(ADMIN_USERS)),
    ctx: PermissionContext = Depends(get_permission_context),
) -> List[UserWithRolesResponse]:
    q = db.query(User).filter(User.company_id == ctx.company_id)
    if site_id:
        user_ids = [
            r.user_id
            for r in db.query(UserSiteRole)
            .filter(
                UserSiteRole.company_id == ctx.company_id,
                (UserSiteRole.site_id == site_id) | (UserSiteRole.site_id.is_(None)),
            )
            .all()
        ]
        q = q.filter(User.id.in_(user_ids))
    users = q.order_by(User.created_at.desc()).all()
    return [_user_with_roles(db, u) for u in users]


@router.post("/users/{user_id}/request-role-change", response_model=RoleChangeRequestResponse)
def request_role_change(
    user_id: UUID,
    payload: RoleChangeRequestCreate,
    db: Session = Depends(get_db),
    ctx: PermissionContext = Depends(get_permission_context),
) -> RoleChangeRequest:
    target = db.query(User).filter(User.id == user_id, User.company_id == ctx.company_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if ctx.user_id != user_id and ADMIN_USERS not in ctx.permissions:
        raise HTTPException(status_code=403, detail="Sin permiso para solicitar cambio de rol ajeno")

    req = RoleChangeRequest(
        user_id=user_id,
        company_id=ctx.company_id,
        site_id=payload.site_id,
        requested_role=payload.requested_role,
        requested_by_id=ctx.user_id,
        reason=payload.reason,
        status=RoleChangeStatus.PENDING,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


@router.get("/role-change-requests", response_model=List[RoleChangeRequestResponse])
def list_role_change_requests(
    status_filter: RoleChangeStatus = Query(RoleChangeStatus.PENDING, alias="status"),
    db: Session = Depends(get_db),
    _: User = Depends(RequirePermission(ADMIN_USERS)),
    ctx: PermissionContext = Depends(get_permission_context),
) -> List[RoleChangeRequest]:
    return (
        db.query(RoleChangeRequest)
        .filter(RoleChangeRequest.company_id == ctx.company_id, RoleChangeRequest.status == status_filter)
        .order_by(RoleChangeRequest.created_at.desc())
        .all()
    )


@router.post("/role-change-requests/{request_id}/approve", response_model=RoleChangeRequestResponse)
def approve_role_change(
    request_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    ctx: PermissionContext = Depends(get_permission_context),
    _: User = Depends(RequirePermission(ADMIN_USERS)),
) -> RoleChangeRequest:
    req = (
        db.query(RoleChangeRequest)
        .filter(RoleChangeRequest.id == request_id, RoleChangeRequest.company_id == ctx.company_id)
        .first()
    )
    if not req or req.status != RoleChangeStatus.PENDING:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada o ya procesada")

    role_q = db.query(UserSiteRole).filter(
        UserSiteRole.user_id == req.user_id,
        UserSiteRole.company_id == ctx.company_id,
    )
    if req.site_id:
        role_q = role_q.filter(UserSiteRole.site_id == req.site_id)
    else:
        role_q = role_q.filter(UserSiteRole.site_id.is_(None))
    usr_row = role_q.first()
    if usr_row:
        usr_row.role = req.requested_role
    else:
        db.add(
            UserSiteRole(
                user_id=req.user_id,
                company_id=ctx.company_id,
                site_id=req.site_id,
                role=req.requested_role,
            )
        )
    user = db.query(User).filter(User.id == req.user_id).first()
    if user and req.site_id is None:
        user.role = req.requested_role

    req.status = RoleChangeStatus.APPROVED
    req.approved_by_id = ctx.user_id
    db.commit()
    db.refresh(req)

    PermissionService(db).log_action(
        user_id=ctx.user_id,
        company_id=ctx.company_id,
        action="role_change_approved",
        resource="user",
        resource_id=req.user_id,
        changes={"requested_role": req.requested_role.value},
        request=request,
        site_id=req.site_id,
    )
    return req


@router.post("/role-change-requests/{request_id}/reject", response_model=RoleChangeRequestResponse)
def reject_role_change(
    request_id: UUID,
    db: Session = Depends(get_db),
    ctx: PermissionContext = Depends(get_permission_context),
    _: User = Depends(RequirePermission(ADMIN_USERS)),
) -> RoleChangeRequest:
    req = (
        db.query(RoleChangeRequest)
        .filter(RoleChangeRequest.id == request_id, RoleChangeRequest.company_id == ctx.company_id)
        .first()
    )
    if not req or req.status != RoleChangeStatus.PENDING:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada o ya procesada")
    req.status = RoleChangeStatus.REJECTED
    req.approved_by_id = ctx.user_id
    db.commit()
    db.refresh(req)
    return req


@router.post(
    "/users/{user_id}/temporary-permissions",
    response_model=TemporaryPermissionResponse,
    status_code=status.HTTP_201_CREATED,
)
def grant_temporary_permission(
    user_id: UUID,
    payload: TemporaryPermissionGrant,
    request: Request,
    db: Session = Depends(get_db),
    ctx: PermissionContext = Depends(get_permission_context),
    _: User = Depends(RequirePermission(ADMIN_USERS)),
) -> TemporaryPermission:
    target = db.query(User).filter(User.id == user_id, User.company_id == ctx.company_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    expires = utc_now() + timedelta(days=payload.expires_in_days)
    row = TemporaryPermission(
        user_id=user_id,
        company_id=ctx.company_id,
        site_id=payload.site_id,
        permission=payload.permission,
        expires_at=expires,
        granted_by_id=ctx.user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    PermissionService(db).log_action(
        user_id=ctx.user_id,
        company_id=ctx.company_id,
        action="temp_permission_granted",
        resource="user",
        resource_id=user_id,
        changes={"permission": payload.permission, "expires_at": expires.isoformat()},
        request=request,
        site_id=payload.site_id,
    )
    return row


@router.delete(
    "/users/{user_id}/temporary-permissions/{tp_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def revoke_temporary_permission(
    user_id: UUID,
    tp_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(RequirePermission(ADMIN_USERS)),
    ctx: PermissionContext = Depends(get_permission_context),
) -> Response:
    row = (
        db.query(TemporaryPermission)
        .filter(
            TemporaryPermission.id == tp_id,
            TemporaryPermission.user_id == user_id,
            TemporaryPermission.company_id == ctx.company_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Permiso temporal no encontrado")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/audit-logs", response_model=List[AuditLogResponse])
def list_audit_logs(
    user_id: Optional[UUID] = Query(None),
    action: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(RequirePermission(ADMIN_USERS)),
    ctx: PermissionContext = Depends(get_permission_context),
) -> list:
    from app.db.models.audit_log import AuditLog

    q = db.query(AuditLog).filter(AuditLog.company_id == ctx.company_id)
    if user_id:
        q = q.filter(AuditLog.user_id == user_id)
    if action:
        q = q.filter(AuditLog.action == action)
    return q.order_by(AuditLog.created_at.desc()).limit(limit).all()
