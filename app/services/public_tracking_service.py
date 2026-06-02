"""Consulta pública de estado de orden por slug + tracking_code."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Generator

from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.core.enums import OrderStatus
from app.db.models.company import Company
from app.db.models.service_order import ServiceOrder
from app.db.session import SessionLocal, catalog_session_scope, tenant_engine_manager
from app.schemas.public_tracking import PublicOrderTrackingResponse
from app.services.tracking_urls import company_public_tracking_enabled
from app.tenancy.exceptions import TenantResolveError
from app.tenancy.resolver import tenant_resolver

_NOT_FOUND = "No encontramos una orden con ese código"

_STATUS_LABELS: dict[OrderStatus, str] = {
    OrderStatus.RECEIVED: "Recibido",
    OrderStatus.DIAGNOSING: "En diagnóstico",
    OrderStatus.WAITING_PARTS: "Esperando repuestos",
    OrderStatus.IN_REPAIR: "En reparación",
    OrderStatus.COMPLETED: "Reparación finalizada",
    OrderStatus.DELIVERED: "Entregado",
    OrderStatus.CANCELLED: "Cancelada",
}


def _status_message(status: OrderStatus, *, delivered_at: datetime | None) -> str:
    if status == OrderStatus.CANCELLED:
        return "Orden cancelada"
    if status == OrderStatus.COMPLETED:
        return "Reparación finalizada — puede retirar su equipo"
    if status == OrderStatus.DELIVERED:
        if delivered_at:
            return f"Entregado el {delivered_at.strftime('%d/%m/%Y')}"
        return "Entregado"
    return "Su equipo está en taller"


def _mask_serial(serial: str | None) -> str:
    if not serial:
        return "oculto"
    s = serial.strip()
    if len(s) <= 4:
        return "oculto"
    return f"***{s[-4:]}"


def _problem_summary(description: str | None) -> str:
    if not description or not description.strip():
        return "En revisión"
    text = description.strip()
    if len(text) > 120:
        return text[:117] + "..."
    return text


@contextmanager
def tenant_db_for_public_slug(slug: str) -> Generator[Session, None, None]:
    slug_key = slug.strip().lower()
    if not settings.USE_TENANT_DATABASE_ROUTING:
        if slug_key != "default":
            raise TenantResolveError("slug inválido")
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
        return

    with catalog_session_scope() as catalog_db:
        info = tenant_resolver.resolve_by_slug(catalog_db, slug_key)
    from sqlalchemy.orm import sessionmaker

    eng = tenant_engine_manager.get_engine(info.database_url)
    TenantSession = sessionmaker(autocommit=False, autoflush=False, bind=eng, class_=Session)
    db = TenantSession()
    try:
        yield db
    finally:
        db.close()


def get_public_order_tracking(
    *,
    tenant_slug: str,
    tracking_code: str,
) -> PublicOrderTrackingResponse:
    code = tracking_code.upper().strip()
    try:
        with tenant_db_for_public_slug(tenant_slug) as db:
            order = (
                db.query(ServiceOrder)
                .options(
                    joinedload(ServiceOrder.company),
                    joinedload(ServiceOrder.site),
                    joinedload(ServiceOrder.equipment),
                    joinedload(ServiceOrder.timeline_entries),
                )
                .filter(ServiceOrder.tracking_code == code)
                .first()
            )
    except TenantResolveError:
        raise LookupError(_NOT_FOUND) from None

    if not order:
        raise LookupError(_NOT_FOUND)

    company: Company | None = order.company
    if not company_public_tracking_enabled(company):
        raise PermissionError("Seguimiento público no disponible; contacte al taller")

    status = order.status or OrderStatus.RECEIVED
    delivered_at = order.actual_completion
    if status == OrderStatus.DELIVERED and not delivered_at and order.timeline_entries:
        for entry in sorted(order.timeline_entries, key=lambda e: e.changed_at, reverse=True):
            if entry.new_status == OrderStatus.DELIVERED.value:
                delivered_at = entry.changed_at
                break

    equipment = order.equipment
    site = order.site

    return PublicOrderTrackingResponse(
        workshop_name=company.name if company else "Taller",
        site_name=site.name if site else None,
        order_number=order.order_number,
        tracking_code=code,
        status=status.value,
        status_label=_STATUS_LABELS.get(status, status.value),
        status_message=_status_message(status, delivered_at=delivered_at),
        received_at=order.received_at,
        estimated_completion=order.estimated_completion,
        delivered_at=delivered_at if status in (OrderStatus.DELIVERED, OrderStatus.COMPLETED) else None,
        equipment_type=getattr(equipment, "equipment_type", None) if equipment else None,
        equipment_brand=getattr(equipment, "brand", None) if equipment else None,
        equipment_model=getattr(equipment, "model", None) if equipment else None,
        serial_masked=_mask_serial(getattr(equipment, "serial_number", None) if equipment else None),
        problem_summary=_problem_summary(order.problem_description),
    )
