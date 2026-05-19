"""Registro de instalaciones desktop (puestos) en catálogo."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.dt import utc_now
from app.core.plan_desktop_policy import desktop_policy_for_plan
from app.db.catalog.models import TenantInstallation
from app.db.models.company import Company


def _active_seat_count(db: Session, company_id: UUID) -> int:
    return (
        db.query(TenantInstallation)
        .filter(
            TenantInstallation.company_id == company_id,
            TenantInstallation.revoked_at.is_(None),
        )
        .count()
    )


def register_or_touch_installation(
    catalog_db: Session,
    *,
    company_id: UUID,
    installation_id: str,
    hostname: str | None,
    plan_code: str,
) -> TenantInstallation:
    """Registra puesto o actualiza last_seen si la instalación ya existe y no está revocada."""
    installation_id = installation_id.strip()
    if not installation_id:
        raise HTTPException(status_code=400, detail="installation_id es obligatorio")

    policy = desktop_policy_for_plan(plan_code)
    existing = (
        catalog_db.query(TenantInstallation)
        .filter(
            TenantInstallation.company_id == company_id,
            TenantInstallation.installation_id == installation_id,
        )
        .first()
    )
    now = utc_now()
    if existing:
        if existing.revoked_at is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Esta instalación fue revocada. Libere el puesto en plataforma o use otro equipo.",
            )
        existing.last_seen_at = now
        if hostname:
            existing.hostname = hostname
        catalog_db.add(existing)
        catalog_db.flush()
        return existing

    active = _active_seat_count(catalog_db, company_id)
    if active >= policy.active_seats_limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cupo de puestos desktop agotado ({policy.active_seats_limit}). "
            "Revoca una instalación en plataforma.",
        )

    row = TenantInstallation(
        id=uuid4(),
        company_id=company_id,
        installation_id=installation_id,
        hostname=hostname,
        activated_at=now,
        last_seen_at=now,
        revoked_at=None,
    )
    catalog_db.add(row)
    catalog_db.flush()
    return row


def revoke_installation(catalog_db: Session, seat_id: UUID, company_id: UUID) -> TenantInstallation:
    row = (
        catalog_db.query(TenantInstallation)
        .filter(TenantInstallation.id == seat_id, TenantInstallation.company_id == company_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Instalación no encontrada")
    if row.revoked_at is None:
        row.revoked_at = utc_now()
        catalog_db.add(row)
        catalog_db.flush()
    return row


def is_seat_revoked(catalog_db: Session, seat_id: UUID, company_id: UUID) -> bool:
    row = (
        catalog_db.query(TenantInstallation)
        .filter(TenantInstallation.id == seat_id, TenantInstallation.company_id == company_id)
        .first()
    )
    if not row:
        return True
    return row.revoked_at is not None


def list_installations(catalog_db: Session, company_id: UUID) -> list[TenantInstallation]:
    return (
        catalog_db.query(TenantInstallation)
        .filter(TenantInstallation.company_id == company_id)
        .order_by(TenantInstallation.activated_at.desc())
        .all()
    )
