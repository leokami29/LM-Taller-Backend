"""Gestión de instalaciones desktop (puestos) desde plataforma."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.permissions import PLATFORM_COMPANIES_READ, PLATFORM_COMPANIES_WRITE
from app.db.session import catalog_session_scope
from app.dependencies import RequirePlatformPermission
from app.schemas.license import TenantInstallationResponse
from app.config import settings
from app.db.catalog.models import CatalogAuditLog
from app.db.models.platform_user import PlatformUser
from app.services.installation_service import list_installations, revoke_installation
from app.services.permission_service import get_catalog_subscription_period_end
from app.services.tenant_config_events import (
    TenantConfigReason,
    company_patch_meta,
    post_company_mutation,
)
from app.db.session import tenant_session_for_company
from app.db.models.company import Company

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
    actor: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_WRITE)),
) -> TenantInstallationResponse:
    with catalog_session_scope() as catalog_db:
        row = revoke_installation(catalog_db, seat_id, company_id)
        catalog_db.add(
            CatalogAuditLog(
                actor_type="platform",
                actor_id=str(actor.id),
                company_id=company_id,
                action="installation_revoked",
                resource_type="tenant_installation",
                resource_id=str(seat_id),
                metadata_json={"installation_id": row.installation_id},
            )
        )
        catalog_db.commit()
    if settings.USE_TENANT_DATABASE_ROUTING:
        period_end = get_catalog_subscription_period_end(company_id)
        meta: dict = {
            "installation_revoked": True,
            "installation_id": row.installation_id,
        }
        with tenant_session_for_company(company_id) as tenant_db:
            company = tenant_db.query(Company).filter(Company.id == company_id).first()
            if company:
                meta = {
                    **company_patch_meta(company, current_period_end=period_end),
                    **meta,
                }
        post_company_mutation(company_id, TenantConfigReason.SUBSCRIPTION, meta=meta)
    return TenantInstallationResponse.model_validate(row)
