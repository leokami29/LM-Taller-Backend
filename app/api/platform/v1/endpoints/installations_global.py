"""Listado global de instalaciones desktop (plataforma)."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.permissions import PLATFORM_COMPANIES_READ
from app.db.session import catalog_session_scope
from app.dependencies import RequirePlatformPermission
from app.schemas.license import TenantInstallationResponse
from app.services.installation_service import list_all_installations

router = APIRouter(prefix="/installations", tags=["platform-installations"])


@router.get("", response_model=list[TenantInstallationResponse])
def list_installations_global(
    company_id: Optional[UUID] = Query(None),
    active_only: bool = Query(False),
    _: None = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_READ)),
) -> list[TenantInstallationResponse]:
    with catalog_session_scope() as catalog_db:
        rows = list_all_installations(
            catalog_db,
            company_id=company_id,
            include_revoked=not active_only,
        )
        return [TenantInstallationResponse.model_validate(r) for r in rows]
