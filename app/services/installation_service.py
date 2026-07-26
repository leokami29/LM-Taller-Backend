"""Registro de instalaciones desktop (puestos) en catálogo."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.dt import utc_now
from app.db.catalog.models import TenantInstallation
from app.services.plan_catalog_service import desktop_policy_for_plan_code


def _active_seat_count(db: Session, company_id: UUID) -> int:
    return (
        db.query(TenantInstallation)
        .filter(
            TenantInstallation.company_id == company_id,
            TenantInstallation.revoked_at.is_(None),
        )
        .count()
    )


def _advisory_lock_company_seats(catalog_db: Session, company_id: UUID) -> None:
    """Serializa altas de puestos por empresa (evita carrera al límite de seats)."""
    lock_key = int(company_id.int % (2**63 - 1))
    catalog_db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": lock_key})


def register_or_touch_installation(
    catalog_db: Session,
    *,
    company_id: UUID,
    installation_id: str,
    hostname: str | None,
    plan_code: str,
    last_successful_sync_at: datetime | None = None,
) -> TenantInstallation:
    """Registra puesto o actualiza last_seen si la instalación ya existe y no está revocada."""
    installation_id = installation_id.strip()
    if not installation_id:
        raise HTTPException(status_code=400, detail="installation_id es obligatorio")

    policy = desktop_policy_for_plan_code(catalog_db, plan_code)
    _advisory_lock_company_seats(catalog_db, company_id)
    existing = (
        catalog_db.query(TenantInstallation)
        .filter(
            TenantInstallation.company_id == company_id,
            TenantInstallation.installation_id == installation_id,
        )
        .with_for_update()
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
        if last_successful_sync_at is not None:
            existing.last_successful_sync_at = last_successful_sync_at
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


def list_all_installations(
    catalog_db: Session,
    *,
    company_id: UUID | None = None,
    include_revoked: bool = True,
) -> list[TenantInstallation]:
    q = catalog_db.query(TenantInstallation)
    if company_id is not None:
        q = q.filter(TenantInstallation.company_id == company_id)
    if not include_revoked:
        q = q.filter(TenantInstallation.revoked_at.is_(None))
    return q.order_by(TenantInstallation.last_successful_sync_at.desc().nulls_last()).all()


def record_installation_sync(
    catalog_db: Session,
    *,
    company_id: UUID,
    installation_id: str,
    hostname: str | None,
    plan_code: str,
    synced_at: datetime | None = None,
) -> TenantInstallation:
    """Marca sync exitosa (pull/push) y actualiza last_seen."""
    when = synced_at or utc_now()
    row = register_or_touch_installation(
        catalog_db,
        company_id=company_id,
        installation_id=installation_id,
        hostname=hostname,
        plan_code=plan_code,
        last_successful_sync_at=when,
    )
    return row
