"""Código corto escaneable por empresa (p. ej. TG-260001)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.order_tracking_sequence import OrderTrackingSequence

if TYPE_CHECKING:
    from app.db.models.service_order import ServiceOrder


def allocate_tracking_code(db: Session, *, company_id: UUID) -> str:
    year_suffix = datetime.now(timezone.utc).year % 100
    row = (
        db.query(OrderTrackingSequence)
        .filter(OrderTrackingSequence.company_id == company_id)
        .with_for_update()
        .first()
    )
    if not row:
        row = OrderTrackingSequence(company_id=company_id, next_value=1)
        db.add(row)
        db.flush()
    n = row.next_value
    row.next_value = n + 1
    db.flush()
    return f"TG-{year_suffix:02d}{n:04d}"


def ensure_order_tracking_code(db: Session, order: ServiceOrder) -> str:
    """Asigna tracking_code si la orden aún no tiene (órdenes demo o pre-migración)."""
    if order.tracking_code:
        return order.tracking_code
    code = allocate_tracking_code(db, company_id=order.company_id)
    order.tracking_code = code
    db.flush()
    return code
