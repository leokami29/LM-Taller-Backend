from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.core.dt import utc_now
from app.core.permissions import PLATFORM_COMPANIES_READ
from app.db.catalog.models import Plan, Subscription, TenantInstallation, TenantRouting
from app.db.models.company import Company
from app.db.models.platform_user import PlatformUser
from app.db.models.rbac import Site
from app.db.session import catalog_session_scope, get_db, tenant_engine_manager
from app.dependencies import RequirePlatformPermission
from app.schemas.platform import PlatformAnalyticsResponse
from app.services import plan_catalog_service as pcs

router = APIRouter(prefix="/analytics", tags=["platform-analytics"])


def _count_sites_for_routings(routings: list[TenantRouting]) -> tuple[int, int]:
    """Sedes en data plane: total y activas (is_active)."""
    total_sites = 0
    active_sites = 0
    for row in routings:
        try:
            eng = tenant_engine_manager.get_engine(row.database_url)
            TenantSession = sessionmaker(autocommit=False, autoflush=False, bind=eng, class_=Session)
            tdb = TenantSession()
            try:
                total_sites += (
                    tdb.query(Site).filter(Site.company_id == row.company_id).count()
                )
                active_sites += (
                    tdb.query(Site)
                    .filter(Site.company_id == row.company_id, Site.is_active.is_(True))
                    .count()
                )
            finally:
                tdb.close()
        except Exception:
            continue
    return total_sites, active_sites


@router.get("/", response_model=PlatformAnalyticsResponse)
def get_platform_analytics(
    db: Session = Depends(get_db),
    _user: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_READ)),
) -> PlatformAnalyticsResponse:
    if settings.USE_TENANT_DATABASE_ROUTING:
        total = db.query(TenantRouting).count()
        active = db.query(TenantRouting).filter(TenantRouting.is_active.is_(True)).count()
        routings = db.query(TenantRouting).filter(TenantRouting.is_active.is_(True)).all()
        total_sites, active_sites = _count_sites_for_routings(routings)

        plans_query = (
            db.query(Plan.code, func.count(Subscription.id))
            .join(Subscription, Subscription.plan_id == Plan.id)
            .filter(Subscription.status == "active")
            .group_by(Plan.code)
            .all()
        )

        by_plan = {code: count for code, count in plans_query}

        mrr = 0.0
        expiring_soon = 0
        stale_sync = 0
        seats_full = 0
        now = utc_now()
        horizon = now + timedelta(days=14)
        with catalog_session_scope() as catalog_db:
            prices = {code: pcs.get_plan_definition(catalog_db, code) for code in pcs.PLAN_CODES}
            for code, count in by_plan.items():
                mrr += count * float(prices.get(code, {}).get("monthly_price_cop") or 0)
            expiring_soon = (
                catalog_db.query(Subscription)
                .filter(
                    Subscription.status == "active",
                    Subscription.current_period_end.isnot(None),
                    Subscription.current_period_end <= horizon,
                    Subscription.current_period_end >= now,
                )
                .count()
            )
            stale_cutoff = now - timedelta(days=7)
            stale_sync = (
                catalog_db.query(TenantInstallation)
                .filter(
                    TenantInstallation.revoked_at.is_(None),
                    TenantInstallation.last_successful_sync_at.isnot(None),
                    TenantInstallation.last_successful_sync_at < stale_cutoff,
                )
                .count()
            )
            active_subs = (
                catalog_db.query(Subscription, Plan.code)
                .join(Plan, Plan.id == Subscription.plan_id)
                .filter(Subscription.status == "active")
                .all()
            )
            for sub, plan_code in active_subs:
                policy = pcs.desktop_policy_for_plan_code(catalog_db, plan_code)
                active_seats = (
                    catalog_db.query(TenantInstallation)
                    .filter(
                        TenantInstallation.company_id == sub.company_id,
                        TenantInstallation.revoked_at.is_(None),
                    )
                    .count()
                )
                if active_seats >= policy.active_seats_limit:
                    seats_full += 1

        return PlatformAnalyticsResponse(
            total_tenants=total,
            active_tenants=active,
            total_sites=total_sites,
            active_sites=active_sites,
            total_mrr=mrr,
            by_plan=by_plan,
            subscriptions_expiring_soon=expiring_soon,
            installations_stale_sync=stale_sync,
            seats_at_capacity=seats_full,
        )

    total = db.query(Company).count()
    active = db.query(Company).filter(Company.is_active.is_(True)).count()
    total_sites = db.query(Site).count()
    active_sites = db.query(Site).filter(Site.is_active.is_(True)).count()

    return PlatformAnalyticsResponse(
        total_tenants=total,
        active_tenants=active,
        total_sites=total_sites,
        active_sites=active_sites,
        total_mrr=0.0,
        by_plan={},
    )
