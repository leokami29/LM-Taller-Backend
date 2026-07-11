from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.dt import utc_now
from app.core.enums import OrderPriority, ServiceOrderKind
from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.company import Company


class SlaPolicy(Base):
    """Política de tiempos de respuesta/resolución por tipo de orden y prioridad."""

    __tablename__ = "sla_policies"
    __table_args__ = (
        Index("ix_sla_policies_company_kind_priority", "company_id", "order_kind", "priority"),
    )

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    order_kind: Mapped[ServiceOrderKind | None] = mapped_column(
        SAEnum(ServiceOrderKind, values_callable=lambda x: [e.value for e in x], native_enum=False),
        nullable=True,
    )
    priority: Mapped[OrderPriority | None] = mapped_column(
        SAEnum(OrderPriority, values_callable=lambda x: [e.value for e in x], native_enum=False),
        nullable=True,
    )
    response_time_hours: Mapped[int | None] = mapped_column(Integer)
    resolution_time_hours: Mapped[int | None] = mapped_column(Integer)
    warning_threshold_hours: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    company: Mapped["Company"] = relationship("Company")
