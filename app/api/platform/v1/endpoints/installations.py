"""Gestión de instalaciones desktop (puestos) desde plataforma."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.permissions import PLATFORM_COMPANIES_READ, PLATFORM_COMPANIES_WRITE
from app.db.session import catalog_session_scope
from app.dependencies import RequirePlatformPermission
from app.schemas.license import TenantInstallationResponse
from app.services.installation_service import list_installations, revoke_installation

router = APIRouter(prefix="/companies", tags=["platform-installations"])


@router.get(
    "/{company_id}/installations",
    response_model=list[TenantInstallationResponse],
)
def list_company_installations(
    company_id: UUID,
    _: None = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_READ)),
) -> list[TenantInstallationResponse]:
    with catalog_session_scope() as catalog_db:
        rows = list_installations(catalog_db, company_id)
        return [TenantInstallationResponse.model_validate(r) for r in rows]


@router.post(
    "/{company_id}/installations/{seat_id}/revoke",
    response_model=TenantInstallationResponse,
)
def revoke_company_installation(
    company_id: UUID,
    seat_id: UUID,
    _: None = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_WRITE)),
) -> TenantInstallationResponse:
    with catalog_session_scope() as catalog_db:
        row = revoke_installation(catalog_db, seat_id, company_id)
        catalog_db.commit()
        return TenantInstallationResponse.model_validate(row)
