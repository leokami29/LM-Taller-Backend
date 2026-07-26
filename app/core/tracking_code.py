"""Código corto escaneable por empresa (aleatorio, no secuencial)."""

from __future__ import annotations

import secrets
import string
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.order_tracking_sequence import OrderTrackingSequence
from app.db.models.service_order import ServiceOrder as ServiceOrderModel

if TYPE_CHECKING:
    from app.db.models.service_order import ServiceOrder

_ALPHABET = string.ascii_uppercase + string.digits
# ~128 bits con A-Z0-9: log2(36^25) ≈ 129. Sobre columna String(40) cabe "TG-" + 25.
_TOKEN_LEN = 25


def _random_token() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(_TOKEN_LEN))


def allocate_tracking_code(db: Session, *, company_id: UUID) -> str:
    """Asigna un código no enumerable. Mantiene secuencia legacy solo como contador opcional."""
    # Touch sequence row for concurrency/compatibility with existing migrations/tests.
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
    else:
        row.next_value = int(row.next_value or 1) + 1
        db.flush()

    for _ in range(8):
        code = f"TG-{_random_token()}"
        exists = (
            db.query(ServiceOrderModel.id)
            .filter(
                ServiceOrderModel.company_id == company_id,
                ServiceOrderModel.tracking_code == code,
            )
            .first()
        )
        if not exists:
            return code
    raise RuntimeError("No se pudo generar tracking_code único")


def ensure_order_tracking_code(db: Session, order: ServiceOrder) -> str:
    """Asigna tracking_code si la orden aún no tiene (órdenes demo o pre-migración)."""
    if order.tracking_code:
        return order.tracking_code
    code = allocate_tracking_code(db, company_id=order.company_id)
    order.tracking_code = code
    db.flush()
    return code
