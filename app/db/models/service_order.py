from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import OrderPriority, OrderStatus
from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.company import Company
    from app.db.models.customer import Customer
    from app.db.models.equipment import Equipment
    from app.db.models.user import User


class ServiceOrder(Base):
    __tablename__ = "service_orders"
    __table_args__ = (
        UniqueConstraint("company_id", "order_number", name="uq_service_orders_company_order_number"),
        Index("ix_service_orders_company_status_created", "company_id", "status", "created_at"),
    )

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    order_number: Mapped[str] = mapped_column(String(32), nullable=False)
    equipment_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("equipment.id"), nullable=False)
    current_customer_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    original_owner_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"))
    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus, values_callable=lambda x: [e.value for e in x], native_enum=False),
        default=OrderStatus.RECEIVED,
    )
    priority: Mapped[OrderPriority] = mapped_column(
        SAEnum(OrderPriority, values_callable=lambda x: [e.value for e in x], native_enum=False),
        default=OrderPriority.MEDIUM,
    )
    assigned_to_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    problem_description: Mapped[str] = mapped_column(Text, nullable=False)
    diagnosis_notes: Mapped[str | None] = mapped_column(Text)
    estimated_completion: Mapped[datetime | None] = mapped_column(DateTime)
    actual_completion: Mapped[datetime | None] = mapped_column(DateTime)
    cost_parts: Mapped[Any] = mapped_column(Numeric(12, 2), default=0)
    cost_labor: Mapped[Any] = mapped_column(Numeric(12, 2), default=0)
    total_cost: Mapped[Any] = mapped_column(Numeric(12, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_by_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))

    company: Mapped["Company"] = relationship("Company", back_populates="service_orders")
    equipment: Mapped["Equipment"] = relationship("Equipment")
    current_customer: Mapped["Customer"] = relationship("Customer", foreign_keys=[current_customer_id])
    original_owner: Mapped["Customer | None"] = relationship("Customer", foreign_keys=[original_owner_id])
    assigned_technician: Mapped["User | None"] = relationship(
        "User", foreign_keys=[assigned_to_id], back_populates="assigned_orders"
    )
    created_by: Mapped["User | None"] = relationship(
        "User", foreign_keys=[created_by_id], back_populates="orders_created"
    )
    timeline_entries: Mapped[list["ServiceOrderTimeline"]] = relationship(
        "ServiceOrderTimeline", back_populates="service_order", cascade="all, delete-orphan"
    )


class ServiceOrderTimeline(Base):
    __tablename__ = "service_order_timeline"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    service_order_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("service_orders.id"), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String(32))
    new_status: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_by_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    time_spent_seconds: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)

    service_order: Mapped["ServiceOrder"] = relationship("ServiceOrder", back_populates="timeline_entries")
    changed_by: Mapped["User | None"] = relationship("User")
