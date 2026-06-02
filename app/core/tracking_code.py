"""Código corto escaneable por empresa (p. ej. TG-260001)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.order_tracking_sequence import OrderTrackingSequence


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
