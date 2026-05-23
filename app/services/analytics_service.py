from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.core.dt import utc_now
from app.core.enums import OrderStatus, UserRole
from app.db.models.customer import Customer
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


def revenue_analytics(
    db: Session,
    *,
    company_id,
    months: int = 12,
) -> dict[str, Any]:
    from app.core.enums import OrderStatus as OS

    completed_statuses = [OS.COMPLETED, OS.DELIVERED]

    cutoff = utc_now() - timedelta(days=months * 30)

    rows = (
        db.query(
            func.date_trunc("month", ServiceOrder.created_at).label("month"),
            func.sum(ServiceOrder.total_cost).label("revenue"),
        )
        .filter(
            ServiceOrder.company_id == company_id,
            ServiceOrder.created_at >= cutoff,
            ServiceOrder.status.in_(completed_statuses),
        )
        .group_by("month")
        .order_by("month")
        .all()
    )

    by_status_res = (
        db.query(
            func.date_trunc("month", ServiceOrder.created_at).label("month"),
            ServiceOrder.status,
            func.sum(ServiceOrder.total_cost).label("revenue"),
        )
        .filter(
            ServiceOrder.company_id == company_id,
            ServiceOrder.created_at >= cutoff,
            ServiceOrder.status.in_(completed_statuses),
        )
        .group_by("month", ServiceOrder.status)
        .order_by("month")
        .all()
    )

    by_month_revenue: dict[str, float] = {}
    for r in rows:
        key = r.month.strftime("%Y-%m") if r.month else "unknown"
        by_month_revenue[key] = float(r.revenue or 0)

    by_month_status: dict[str, dict[str, float]] = {}
    for r in by_status_res:
        key = r.month.strftime("%Y-%m") if r.month else "unknown"
        if key not in by_month_status:
            by_month_status[key] = {}
        by_month_status[key][r.status.value] = float(r.revenue or 0)

    totals_by_status: dict[str, float] = {}
    for r in by_status_res:
        s = r.status.value
        totals_by_status[s] = totals_by_status.get(s, 0) + float(r.revenue or 0)

    return {
        "by_month": by_month_revenue,
        "by_month_status": by_month_status,
        "totals_by_status": totals_by_status,
        "total_revenue": sum(by_month_revenue.values()),
        "months": months,
    }


def customer_analytics(
    db: Session,
    *,
    company_id,
    top_n: int = 10,
) -> dict[str, Any]:
    from app.core.enums import OrderStatus as OS

    completed_statuses = [OS.COMPLETED, OS.DELIVERED]

    top_customers = (
        db.query(
            Customer.id,
            Customer.first_name,
            Customer.last_name,
            func.count(ServiceOrder.id).label("order_count"),
            func.sum(ServiceOrder.total_cost).label("total_spent"),
        )
        .join(ServiceOrder, ServiceOrder.current_customer_id == Customer.id)
        .filter(
            Customer.company_id == company_id,
            ServiceOrder.status.in_(completed_statuses),
        )
        .group_by(Customer.id, Customer.first_name, Customer.last_name)
        .order_by(func.count(ServiceOrder.id).desc())
        .limit(top_n)
        .all()
    )

    thirty_days_ago = utc_now() - timedelta(days=30)
    new_customers = (
        db.query(func.count(Customer.id))
        .filter(
            Customer.company_id == company_id,
            Customer.created_at >= thirty_days_ago,
        )
        .scalar()
        or 0
    )

    total_customers = (
        db.query(func.count(Customer.id))
        .filter(Customer.company_id == company_id)
        .scalar()
        or 0
    )

    return {
        "top_customers": [
            {
                "customer_id": str(r.id),
                "first_name": r.first_name,
                "last_name": r.last_name,
                "order_count": int(r.order_count or 0),
                "total_spent": float(r.total_spent or 0),
            }
            for r in top_customers
        ],
        "new_customers_30d": int(new_customers),
        "total_customers": int(total_customers),
    }
