"""Dependencias FastAPI por contexto (tenant, plataforma, portal, permisos)."""

from app.api.deps.permissions import (
    PermissionContext,
    RequirePermission,
    ensure_not_viewer_for_mutation,
    get_permission_context,
)
from app.api.deps.platform_auth import (
    RequirePlatformPermission,
    get_current_platform_user,
    require_platform_super_admin,
)
from app.api.deps.portal_auth import (
    PortalContext,
    get_current_portal_user,
    get_portal_context,
)
from app.api.deps.tenant_auth import (
    get_current_admin,
    get_current_technician_or_admin,
    get_current_user,
    require_roles,
)

__all__ = [
    "PermissionContext",
    "PortalContext",
    "RequirePermission",
    "RequirePlatformPermission",
    "ensure_not_viewer_for_mutation",
    "get_current_admin",
    "get_current_platform_user",
    "get_current_portal_user",
    "get_current_technician_or_admin",
    "get_current_user",
    "get_permission_context",
    "get_portal_context",
    "require_platform_super_admin",
    "require_roles",
]
