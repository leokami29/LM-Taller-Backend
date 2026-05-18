"""Reglas de vigencia de suscripción (estado + fin de período)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.core.dt import utc_now
from app.core.enums import SubscriptionStatus

BlockReason = Literal["status", "period_expired"]


def is_period_expired(
    period_end: datetime | None,
    *,
    now: datetime | None = None,
) -> bool:
    if period_end is None:
        return False
    reference = now or utc_now()
    end = period_end
    if end.tzinfo is None and reference.tzinfo is not None:
        end = end.replace(tzinfo=reference.tzinfo)
    elif end.tzinfo is not None and reference.tzinfo is None:
        reference = reference.replace(tzinfo=end.tzinfo)
    return end < reference


def subscription_is_usable(
    status: SubscriptionStatus | str,
    period_end: datetime | None = None,
    *,
    now: datetime | None = None,
) -> bool:
    try:
        st = SubscriptionStatus(status)
    except ValueError:
        return False
    if st not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL):
        return False
    if is_period_expired(period_end, now=now):
        return False
    return True


def subscription_block_reason(
    status: SubscriptionStatus | str,
    period_end: datetime | None = None,
    *,
    now: datetime | None = None,
) -> BlockReason | None:
    if subscription_is_usable(status, period_end, now=now):
        return None
    try:
        st = SubscriptionStatus(status)
    except ValueError:
        return "status"
    if st not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL):
        return "status"
    if is_period_expired(period_end, now=now):
        return "period_expired"
    return "status"


def validate_subscription_period_status(
    status: SubscriptionStatus,
    period_end: datetime | None,
) -> None:
    """Lanza ValueError si active/trial tienen fin de período ya vencido."""
    if subscription_is_usable(status, period_end):
        return
    if subscription_block_reason(status, period_end) == "period_expired":
        raise ValueError(
            "No se puede dejar la suscripción en active o trial con un fin de período "
            "anterior a la fecha actual. Cambiá el estado (p. ej. cancelada) o elegí "
            "una fecha futura."
        )
