"""Entitlements efectivos de un taller (plan + límites + módulos)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.enums import PlanTier, SubscriptionStatus
from app.core.features import MODULE_CORE, PLAN_DEFAULTS


@dataclass(frozen=True)
class Entitlements:
    plan: PlanTier
    status: SubscriptionStatus
    modules: frozenset[str]
    max_users: int | None
    max_orders_month: int | None
    storage_mb: int | None

    def is_subscription_usable(self) -> bool:
        return self.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL)

    def has_module(self, module: str) -> bool:
        return module in self.modules or module == MODULE_CORE

    def limit(self, key: str) -> int | None:
        if key == "max_users":
            return self.max_users
        if key == "max_orders_month":
            return self.max_orders_month
        if key == "storage_mb":
            return self.storage_mb
        return None

    @classmethod
    def from_company_row(
        cls,
        *,
        plan: PlanTier | str | None,
        subscription_status: SubscriptionStatus | str | None,
        active_users_limit: int | None,
        settings_json: dict[str, Any] | None = None,
    ) -> Entitlements:
        tier = PlanTier(plan) if plan else PlanTier.STARTER
        status = (
            SubscriptionStatus(subscription_status)
            if subscription_status
            else SubscriptionStatus.ACTIVE
        )
        defaults = PLAN_DEFAULTS.get(tier.value, PLAN_DEFAULTS["starter"])
        settings = settings_json or {}
        ent = settings.get("entitlements") or {}
        modules_raw = ent.get("modules") or list(defaults["modules"])
        return cls(
            plan=tier,
            status=status,
            modules=frozenset(str(m) for m in modules_raw),
            max_users=active_users_limit if active_users_limit is not None else defaults["max_users"],
            max_orders_month=ent.get("max_orders_month", defaults["max_orders_month"]),
            storage_mb=ent.get("storage_mb", defaults["storage_mb"]),
        )

    @classmethod
    def default_starter(cls) -> Entitlements:
        return cls.from_company_row(plan=PlanTier.STARTER, subscription_status=SubscriptionStatus.ACTIVE, active_users_limit=5)
