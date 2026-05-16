from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.core.permissions import PLATFORM_COMPANIES_READ
from app.db.catalog.models import Plan, Subscription, TenantRouting
from app.db.models.company import Company
from app.db.models.platform_user import PlatformUser
from app.db.models.rbac import Site
from app.db.session import get_db, tenant_engine_manager
from app.dependencies import RequirePlatformPermission
from app.schemas.platform import PlatformAnalyticsResponse

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
        mrr += by_plan.get("pro", 0) * 29000
        mrr += by_plan.get("enterprise", 0) * 99000

        return PlatformAnalyticsResponse(
            total_tenants=total,
            active_tenants=active,
            total_sites=total_sites,
            active_sites=active_sites,
            total_mrr=mrr,
            by_plan=by_plan,
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
