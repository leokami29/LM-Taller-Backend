"""Licencia desktop firmada y estado liviano."""

from __future__ import annotations

from typing import Annotated, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import settings
from app.db.catalog.models import TenantRouting
from app.db.models.company import Company
from app.db.models.user import User
from app.db.session import catalog_session_scope, tenant_session_for_company
from app.core.permissions import ADMIN_USERS
from app.dependencies import RequirePermission, get_current_user
from app.schemas.license import (
    LicenseStatusResponse,
    SignedLicenseManifest,
)
from app.services.installation_service import is_seat_revoked, register_or_touch_installation
from app.services.license_manifest_service import build_license_manifest
from app.services.permission_service import PermissionService
from app.services.tenant_config_events import read_company_config_revision, read_global_config_revision

router = APIRouter(prefix="/license", tags=["license"])


def _tenant_slug_for_company(company_id: UUID) -> str:
    if not settings.USE_TENANT_DATABASE_ROUTING:
        return "default"
    with catalog_session_scope() as catalog_db:
        row = catalog_db.query(TenantRouting).filter(TenantRouting.company_id == company_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Tenant slug no encontrado")
        return row.slug


@router.get("/manifest", response_model=SignedLicenseManifest)
def get_license_manifest(
    installation_id: Annotated[str, Query(min_length=8, max_length=128)],
    hostname: Annotated[Optional[str], Query(max_length=255)] = None,
    current_user: User = Depends(RequirePermission(ADMIN_USERS)),
) -> SignedLicenseManifest:
    with tenant_session_for_company(current_user.company_id) as db:
        company = db.query(Company).filter(Company.id == current_user.company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail="Empresa no encontrada")
        svc = PermissionService(db)
        if not svc.is_company_subscription_usable(current_user.company_id):
            raise HTTPException(status_code=403, detail="Suscripción no permite emitir licencia desktop")
        tenant_slug = _tenant_slug_for_company(current_user.company_id)
        seat_id = uuid4()
        if settings.USE_TENANT_DATABASE_ROUTING:
            with catalog_session_scope() as catalog_db:
                seat = register_or_touch_installation(
                    catalog_db,
                    company_id=current_user.company_id,
                    installation_id=installation_id,
                    hostname=hostname,
                    plan_code=company.plan.value,
                )
                catalog_db.commit()
                seat_id = seat.id
        return build_license_manifest(
            db,
            company=company,
            tenant_slug=tenant_slug,
            seat_id=seat_id,
            installation_id=installation_id,
        )


@router.get("/status", response_model=LicenseStatusResponse)
def license_status(
    seat_id: Annotated[Optional[UUID], Query()] = None,
    current_user: User = Depends(get_current_user),
) -> LicenseStatusResponse:
    with tenant_session_for_company(current_user.company_id) as db:
        company = db.query(Company).filter(Company.id == current_user.company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail="Empresa no encontrada")
        svc = PermissionService(db)
        ent = svc.get_entitlements(current_user.company_id)
        period_end = svc.get_subscription_period_end(current_user.company_id)
        usable = svc.is_company_subscription_usable(current_user.company_id)
        revoked = False
        if seat_id and settings.USE_TENANT_DATABASE_ROUTING:
            with catalog_session_scope() as catalog_db:
                revoked = is_seat_revoked(catalog_db, seat_id, current_user.company_id)
        return LicenseStatusResponse(
            config_revision=read_company_config_revision(company),
            global_config_revision=read_global_config_revision(),
            subscription_status=ent.status.value,
            subscription_usable=usable and not revoked,
            license_valid_until=period_end,
            seat_revoked=revoked,
        )
