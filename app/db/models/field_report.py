from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.dt import utc_now
from app.core.enums import FieldReportStatus
from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.company import Company
    from app.db.models.rbac import Site
    from app.db.models.service_order import ServiceOrder
    from app.db.models.user import User


class FieldReport(Base):
    """Reporte técnico de campo, opcionalmente vinculado a una orden de servicio."""

    __tablename__ = "field_reports"
    __table_args__ = (
        Index("ix_field_reports_company_created", "company_id", "created_at"),
        Index("ix_field_reports_order_id", "order_id"),
    )

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False
    )
    site_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id"), nullable=True
    )
    order_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("service_orders.id"), nullable=True
    )
    technician_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    findings: Mapped[str | None] = mapped_column(Text)
    recommendations: Mapped[str | None] = mapped_column(Text)
    status: Mapped[FieldReportStatus] = mapped_column(
        SAEnum(FieldReportStatus, values_callable=lambda x: [e.value for e in x], native_enum=False),
        default=FieldReportStatus.DRAFT,
        nullable=False,
    )
    photos_urls: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    company: Mapped["Company"] = relationship("Company")
    site: Mapped["Site | None"] = relationship("Site")
    order: Mapped["ServiceOrder | None"] = relationship("ServiceOrder")
    technician: Mapped["User"] = relationship("User")
