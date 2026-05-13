from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import ANALYTICS_READ
from app.db.models.user import User
from app.db.session import get_db
from app.dependencies import RequirePermission
from app.services.analytics_service import orders_metrics, technicians_performance

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/orders/metrics")
def get_orders_metrics(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    current_user: User = Depends(RequirePermission(ANALYTICS_READ)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return orders_metrics(
        db,
        company_id=current_user.company_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/technicians/performance")
def get_technicians_performance(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    current_user: User = Depends(RequirePermission(ANALYTICS_READ)),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return technicians_performance(
        db,
        company_id=current_user.company_id,
        date_from=date_from,
        date_to=date_to,
    )
