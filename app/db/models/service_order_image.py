from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.dt import utc_now
from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.service_order import ServiceOrder


class ServiceOrderImage(Base):
    __tablename__ = "service_order_images"
    __table_args__ = (
        Index("ix_service_order_images_order_id", "service_order_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    service_order_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("service_orders.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    caption: Mapped[str | None] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    order: Mapped["ServiceOrder"] = relationship("ServiceOrder", back_populates="images")
