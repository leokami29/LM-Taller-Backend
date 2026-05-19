"""Políticas desktop por plan: grace offline, sync obligatorio y puestos."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.enums import PlanTier


@dataclass(frozen=True)
class DesktopPlanPolicy:
    offline_grace_days: int
    max_days_without_sync: int
    active_seats_limit: int


_DEFAULTS: dict[PlanTier, DesktopPlanPolicy] = {
    PlanTier.STARTER: DesktopPlanPolicy(
        offline_grace_days=7,
        max_days_without_sync=14,
        active_seats_limit=1,
    ),
    PlanTier.PRO: DesktopPlanPolicy(
        offline_grace_days=14,
        max_days_without_sync=30,
        active_seats_limit=3,
    ),
    PlanTier.ENTERPRISE: DesktopPlanPolicy(
        offline_grace_days=30,
        max_days_without_sync=90,
        active_seats_limit=10,
    ),
}


def desktop_policy_for_plan(plan: PlanTier | str) -> DesktopPlanPolicy:
    try:
        tier = PlanTier(plan)
    except ValueError:
        tier = PlanTier.STARTER
    return _DEFAULTS[tier]
