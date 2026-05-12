from datetime import datetime
from typing import Any, Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.core.enums import OrderStatus, UserRole
from app.db.models.service_order import ServiceOrder
from app.db.models.user import User


def orders_metrics(
    db: Session,
    *,
    company_id,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> dict[str, Any]:
    def base_query():
        q = db.query(ServiceOrder).filter(ServiceOrder.company_id == company_id)
        if date_from is not None:
            q = q.filter(ServiceOrder.created_at >= date_from)
        if date_to is not None:
            q = q.filter(ServiceOrder.created_at <= date_to)
        return q

    total = base_query().count()
    by_status: dict[str, int] = {}
    for status in OrderStatus:
        by_status[status.value] = base_query().filter(ServiceOrder.status == status).count()

    return {
        "total_orders": total,
        "by_status": by_status,
        "date_from": date_from,
        "date_to": date_to,
    }


def technicians_performance(
    db: Session,
    *,
    company_id,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    join_cond = [
        ServiceOrder.assigned_to_id == User.id,
        ServiceOrder.company_id == company_id,
    ]
    if date_from is not None:
        join_cond.append(ServiceOrder.created_at >= date_from)
    if date_to is not None:
        join_cond.append(ServiceOrder.created_at <= date_to)

    q = (
        db.query(
            User.id,
            User.full_name,
            func.count(ServiceOrder.id).label("assigned_orders"),
        )
        .outerjoin(ServiceOrder, and_(*join_cond))
        .filter(User.company_id == company_id, User.role == UserRole.TECHNICIAN)
        .group_by(User.id, User.full_name)
    )
    rows = q.all()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "user_id": str(row.id),
                "full_name": row.full_name,
                "assigned_orders": int(row.assigned_orders or 0),
            }
        )
    return out
