from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.dt import utc_now
from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.company import Company
    from app.db.models.customer import Customer


class Equipment(Base):
    __tablename__ = "equipment"
    __table_args__ = (
        UniqueConstraint("company_id", "serial_number", name="uq_equipment_company_serial"),
        Index("ix_equipment_company_id", "company_id"),
    )

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    serial_number: Mapped[str] = mapped_column(String(120), nullable=False)
    equipment_type: Mapped[str | None] = mapped_column(String(120))
    brand: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120))
    imei: Mapped[str | None] = mapped_column(String(32))
    color: Mapped[str | None] = mapped_column(String(64))
    original_owner_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"))
    photos_urls: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    additional_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )
    first_received_date: Mapped[date | None] = mapped_column(Date)

    company: Mapped["Company"] = relationship("Company", back_populates="equipment_list")
    original_owner: Mapped["Customer | None"] = relationship("Customer", foreign_keys=[original_owner_id])
