from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import settings
from app.db.session import get_db
from app.core.permissions import PLATFORM_COMPANIES_READ
from app.dependencies import RequirePlatformPermission
from app.db.catalog.models import TenantRouting, Subscription, Plan
from app.schemas.platform import PlatformAnalyticsResponse
from app.db.models.platform_user import PlatformUser

router = APIRouter(prefix="/analytics", tags=["platform-analytics"])

@router.get("/", response_model=PlatformAnalyticsResponse)
def get_platform_analytics(
    db: Session = Depends(get_db),
    _user: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_READ))
) -> PlatformAnalyticsResponse:
    if settings.USE_TENANT_DATABASE_ROUTING:
        total = db.query(TenantRouting).count()
        active = db.query(TenantRouting).filter(TenantRouting.is_active == True).count()
        
        plans_query = db.query(Plan.code, func.count(Subscription.id)).join(
            Subscription, Subscription.plan_id == Plan.id
        ).filter(Subscription.status == 'active').group_by(Plan.code).all()
        
        by_plan = {code: count for code, count in plans_query}
        
        # Simulación de MRR (Si no hay stripe history aún indexado en la tabla)
        mrr = 0.0
        mrr += by_plan.get('pro', 0) * 29000
        mrr += by_plan.get('enterprise', 0) * 99000
        
        return PlatformAnalyticsResponse(
            total_tenants=total,
            active_tenants=active,
            total_mrr=mrr,
            by_plan=by_plan
        )
    return PlatformAnalyticsResponse(total_tenants=0, active_tenants=0, total_mrr=0.0, by_plan={})
