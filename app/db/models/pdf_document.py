from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.company import Company
    from app.db.models.service_order import ServiceOrder
    from app.db.models.user import User


class PDFDocument(Base):
    __tablename__ = "pdf_documents"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    service_order_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), ForeignKey("service_orders.id"))
    document_type: Mapped[str] = mapped_column(String(80), nullable=False)
    file_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    generated_by_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    company: Mapped["Company"] = relationship("Company", back_populates="pdf_documents")
    service_order: Mapped["ServiceOrder | None"] = relationship("ServiceOrder")
    generated_by: Mapped["User | None"] = relationship("User")
