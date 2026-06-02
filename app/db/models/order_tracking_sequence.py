from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.company import Company


class OrderTrackingSequence(Base):
    __tablename__ = "order_tracking_sequences"
    __table_args__ = (UniqueConstraint("company_id", name="uq_order_tracking_sequences_company"),)

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    next_value: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    company: Mapped["Company"] = relationship("Company")
