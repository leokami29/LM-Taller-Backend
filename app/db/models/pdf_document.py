from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.dt import utc_now
from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.company import Company
    from app.db.models.service_order import ServiceOrder
    from app.db.models.user import User


class PDFDocument(Base):
    __tablename__ = "pdf_documents"
    __table_args__ = (
        Index("ix_pdf_documents_company_id", "company_id"),
        Index("ix_pdf_documents_service_order_id", "service_order_id"),
    )

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    service_order_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("service_orders.id"), nullable=True
    )
    document_type: Mapped[str] = mapped_column(String(80), nullable=False)
    document_format: Mapped[str] = mapped_column(String(16), nullable=False, default="a4")
    file_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    generated_by_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_copy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    company: Mapped["Company"] = relationship("Company", back_populates="pdf_documents")
    service_order: Mapped["ServiceOrder | None"] = relationship("ServiceOrder")
    generated_by: Mapped["User | None"] = relationship("User")
