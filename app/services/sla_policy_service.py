from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.enums import OrderPriority, ServiceOrderKind
from app.db.models.sla_policy import SlaPolicy


def create_sla_policy(
    db: Session,
    *,
    company_id: UUID,
    name: str,
    order_kind: Optional[ServiceOrderKind] = None,
    priority: Optional[OrderPriority] = None,
    response_time_hours: Optional[int] = None,
    resolution_time_hours: Optional[int] = None,
    warning_threshold_hours: int = 6,
    is_active: bool = True,
) -> SlaPolicy:
    policy = SlaPolicy(
        company_id=company_id,
        name=name,
        order_kind=order_kind,
        priority=priority,
        response_time_hours=response_time_hours,
        resolution_time_hours=resolution_time_hours,
        warning_threshold_hours=warning_threshold_hours,
        is_active=is_active,
    )
    db.add(policy)
    db.flush()
    return policy


def update_sla_policy(db: Session, policy: SlaPolicy, data: dict) -> SlaPolicy:
    for key, value in data.items():
        if hasattr(policy, key):
            setattr(policy, key, value)
    db.flush()
    return policy


def delete_sla_policy(db: Session, policy: SlaPolicy) -> None:
    db.delete(policy)
    db.flush()


def find_matching_sla_policy(
    db: Session,
    *,
    company_id: UUID,
    order_kind: ServiceOrderKind,
    priority: OrderPriority,
) -> Optional[SlaPolicy]:
    """Busca la política más específica que aplique al tipo de orden y prioridad.

    Orden de precedencia:
    1. order_kind + priority
    2. order_kind (cualquier prioridad)
    3. priority (cualquier tipo de orden)
    4. política global (sin order_kind ni priority)
    """
    q = db.query(SlaPolicy).filter(
        SlaPolicy.company_id == company_id,
        SlaPolicy.is_active.is_(True),
    )
    candidates = q.order_by(SlaPolicy.created_at.desc()).all()

    best: Optional[SlaPolicy] = None
    best_score = -1
    for p in candidates:
        score = 0
        if p.order_kind == order_kind:
            score += 2
        elif p.order_kind is not None:
            continue
        if p.priority == priority:
            score += 1
        elif p.priority is not None:
            continue
        if score > best_score:
            best_score = score
            best = p
    return best


def compute_estimated_completion(
    db: Session,
    *,
    company_id: UUID,
    order_kind: ServiceOrderKind,
    priority: OrderPriority,
    start_at: datetime,
) -> Optional[datetime]:
    """Calcula la fecha estimada de cumplimiento según la política SLA vigente."""
    policy = find_matching_sla_policy(
        db,
        company_id=company_id,
        order_kind=order_kind,
        priority=priority,
    )
    if not policy or not policy.resolution_time_hours:
        return None
    from datetime import timedelta

    return start_at + timedelta(hours=policy.resolution_time_hours)
