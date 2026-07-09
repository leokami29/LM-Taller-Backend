from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps.tenant_auth import get_current_user
from app.core.enums import UserRole
from app.db.models.user import User
from app.db.session import get_db
from app.services.permission_service import PermissionService


@dataclass
class PermissionContext:
    user: User
    user_id: UUID
    company_id: UUID
    site_id: UUID | None
    role: UserRole
    permissions: frozenset[str]


def _parse_site_id(raw: str | None) -> UUID | None:
    if not raw or not raw.strip():
        return None
    try:
        return UUID(raw.strip())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Site-Id inválido") from exc


def get_permission_context(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    x_site_id: str | None = Header(None, alias="X-Site-Id"),
    site_id_query: UUID | None = None,
) -> PermissionContext:
    svc = PermissionService(db)
    site_id = _parse_site_id(x_site_id)
    if site_id is None and site_id_query is not None:
        site_id = site_id_query
    if site_id is not None and not svc.user_has_site_access(user.id, user.company_id, site_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin acceso a esta sede")
    role = svc.resolve_role_for_site(user.id, user.company_id, site_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rol no asignado")
    perms = svc.get_user_permissions(user.id, user.company_id, site_id)
    return PermissionContext(
        user=user,
        user_id=user.id,
        company_id=user.company_id,
        site_id=site_id,
        role=role,
        permissions=perms,
    )


class RequirePermission:
    """Dependencia: exige permiso tenant recurso:acción (plan ∩ rol sede ∪ temporales)."""

    def __init__(self, permission: str) -> None:
        self.permission = permission

    def __call__(self, ctx: PermissionContext = Depends(get_permission_context)) -> User:
        if self.permission not in ctx.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permiso requerido: {self.permission}",
            )
        return ctx.user


def ensure_not_viewer_for_mutation(subject: User | PermissionContext) -> None:
    role = subject.role if isinstance(subject, PermissionContext) else subject.role
    if role == UserRole.VIEWER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El rol viewer solo puede consultar",
        )
