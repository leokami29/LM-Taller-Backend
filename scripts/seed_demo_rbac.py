"""Plan SaaS denormalizado + sedes y user_site_roles para semillas demo."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.enums import PlanTier, SubscriptionStatus, UserRole
from app.core.features import PLAN_DEFAULTS
from app.db.models.company import Company
from app.db.models.rbac import Site, UserSiteRole
from app.db.models.user import User


def apply_demo_company_plan(
    session: Session,
    company: Company,
    *,
    tier: PlanTier = PlanTier.PRO,
) -> None:
    """Alinea company con un plan demo (Pro por defecto: inventario + analytics)."""
    defaults = PLAN_DEFAULTS[tier.value]
    modules = defaults["modules"]
    company.plan = tier
    company.subscription_status = SubscriptionStatus.ACTIVE
    company.active_users_limit = defaults["max_users"]
    if company.email:
        company.billing_email = company.email

    settings = dict(company.settings_json or {})
    ent = dict(settings.get("entitlements") or {})
    ent["modules"] = sorted(modules)
    ent["max_orders_month"] = defaults["max_orders_month"]
    ent["storage_mb"] = defaults["storage_mb"]
    settings["entitlements"] = ent
    company.settings_json = settings
    session.add(company)


def _get_or_create_site(session: Session, company_id, *, name: str, location: str | None) -> Site:
    row = session.scalar(select(Site).where(Site.company_id == company_id, Site.name == name))
    if row:
        return row
    from app.services.site_code_service import derive_site_code

    existing = {
        row[0]
        for row in session.query(Site.code).filter(Site.company_id == company_id).all()
    }
    code = derive_site_code(name, existing)
    s = Site(
        company_id=company_id,
        code=code,
        name=name,
        location=location or None,
        is_active=True,
    )
    session.add(s)
    session.flush()
    return s


def _clear_company_site_roles(session: Session, company_id) -> None:
    """Evita duplicados si se re-ejecuta lógica sobre usuarios ya existentes."""
    session.execute(delete(UserSiteRole).where(UserSiteRole.company_id == company_id))


def ensure_demo_sites_primary(
    session: Session,
    company: Company,
    *,
    admin: User,
    recep: User,
    recep2: User,
    tech1: User,
    tech2: User,
    tech3: User,
    tech4: User,
    tech5: User,
    viewer: User,
    inactive: User,
) -> tuple[Site, Site, Site]:
    """
    Tres sedes: Principal, Sede Norte y Sede Sur.
    Admin corporativo (site_id NULL). Jorge (tech2) en Principal + Norte.
    Camila (tech3) en Norte, Andrés (tech4) y Felipe (tech5) en Sur.
    Sofía (recep2) en Norte.
    """
    principal = _get_or_create_site(
        session,
        company.id,
        name="Principal",
        location=company.address[:200] if company.address else None,
    )
    norte = _get_or_create_site(
        session,
        company.id,
        name="Sede Norte",
        location="Calle 170 # 15-40, Bogotá — Zona norte",
    )
    sur = _get_or_create_site(
        session,
        company.id,
        name="Sede Sur",
        location="Autopista Sur # 40-25, Bogotá — Zona industrial sur",
    )

    _clear_company_site_roles(session, company.id)
    session.flush()

    # Admin corporativo — sin sede (scope de empresa completo)
    session.add(
        UserSiteRole(
            user_id=admin.id,
            company_id=company.id,
            site_id=None,
            role=UserRole.ADMIN,
            is_active=True,
        )
    )

    # Sede Principal: recep1, tech1, viewer
    for u, role in (
        (recep, UserRole.RECEPTION),
        (tech1, UserRole.TECHNICIAN),
        (viewer, UserRole.VIEWER),
    ):
        session.add(
            UserSiteRole(
                user_id=u.id,
                company_id=company.id,
                site_id=principal.id,
                role=role,
                is_active=True,
            )
        )

    # tech2: Principal + Norte (técnico multi-sede)
    session.add_all(
        [
            UserSiteRole(
                user_id=tech2.id,
                company_id=company.id,
                site_id=principal.id,
                role=UserRole.TECHNICIAN,
                is_active=True,
            ),
            UserSiteRole(
                user_id=tech2.id,
                company_id=company.id,
                site_id=norte.id,
                role=UserRole.TECHNICIAN,
                is_active=True,
            ),
        ]
    )

    # Sede Norte: recep2, tech3
    session.add_all(
        [
            UserSiteRole(
                user_id=recep2.id,
                company_id=company.id,
                site_id=norte.id,
                role=UserRole.RECEPTION,
                is_active=True,
            ),
            UserSiteRole(
                user_id=tech3.id,
                company_id=company.id,
                site_id=norte.id,
                role=UserRole.TECHNICIAN,
                is_active=True,
            ),
        ]
    )

    # Sede Sur: tech4, tech5
    session.add_all(
        [
            UserSiteRole(
                user_id=tech4.id,
                company_id=company.id,
                site_id=sur.id,
                role=UserRole.TECHNICIAN,
                is_active=True,
            ),
            UserSiteRole(
                user_id=tech5.id,
                company_id=company.id,
                site_id=sur.id,
                role=UserRole.TECHNICIAN,
                is_active=True,
            ),
        ]
    )

    # Usuario inactivo — Principal (inactivo)
    session.add(
        UserSiteRole(
            user_id=inactive.id,
            company_id=company.id,
            site_id=principal.id,
            role=UserRole.VIEWER,
            is_active=False,
        )
    )

    session.flush()
    return principal, norte, sur


def ensure_demo_sites_secondary(
    session: Session,
    company: Company,
    *,
    admin: User,
    recep: User,
    tech: User,
) -> Site:
    """Tenant norte: sede principal + punto Boyacá (rol por sede)."""
    principal = _get_or_create_site(
        session,
        company.id,
        name="Principal",
        location=company.address[:200] if company.address else None,
    )
    boyaca = _get_or_create_site(
        session,
        company.id,
        name="Punto Boyacá",
        location="Av. Boyacá — demo sede secundaria",
    )

    _clear_company_site_roles(session, company.id)
    session.flush()

    session.add(
        UserSiteRole(
            user_id=admin.id,
            company_id=company.id,
            site_id=None,
            role=UserRole.ADMIN,
            is_active=True,
        )
    )
    session.add(
        UserSiteRole(
            user_id=recep.id,
            company_id=company.id,
            site_id=principal.id,
            role=UserRole.RECEPTION,
            is_active=True,
        )
    )
    session.add(
        UserSiteRole(
            user_id=tech.id,
            company_id=company.id,
            site_id=principal.id,
            role=UserRole.TECHNICIAN,
            is_active=True,
        )
    )
    session.add(
        UserSiteRole(
            user_id=tech.id,
            company_id=company.id,
            site_id=boyaca.id,
            role=UserRole.TECHNICIAN,
            is_active=True,
        )
    )
    session.flush()
    return principal


def ensure_demo_catalog_subscriptions(
    session: Session,
    *,
    central_company_id,
    norte_company_id,
) -> None:
    """Filas subscriptions en catálogo (tras migración catalog_002)."""
    from app.db.catalog.models import Plan, Subscription

    plan = session.scalar(select(Plan).where(Plan.code == "pro"))
    if plan is None:
        print(
            "[catálogo] Sin fila `plans` (¿falta `alembic -c alembic_catalog.ini upgrade head`?). "
            "Omitiendo subscriptions demo."
        )
        return

    from datetime import timedelta
    from uuid import uuid4

    from app.core.dt import utc_now
    from app.db.catalog.models import BillingEvent

    now = utc_now()
    for cid in (central_company_id, norte_company_id):
        sub = session.scalar(select(Subscription).where(Subscription.company_id == cid))
        if sub:
            sub.plan_id = plan.id
            sub.status = SubscriptionStatus.ACTIVE
            sub.provider = "manual"
        else:
            sub = Subscription(
                company_id=cid,
                plan_id=plan.id,
                status=SubscriptionStatus.ACTIVE,
                provider="manual",
            )
            session.add(sub)
            session.flush()
        existing = session.scalar(
            select(BillingEvent).where(BillingEvent.company_id == cid).limit(1)
        )
        if not existing:
            session.add(
                BillingEvent(
                    id=uuid4(),
                    company_id=cid,
                    subscription_id=sub.id,
                    amount_cop=99000,
                    status="paid",
                    period_start=now - timedelta(days=30),
                    period_end=now,
                    paid_at=now,
                    notes="Seed demo — pago mock",
                )
            )
    session.flush()
