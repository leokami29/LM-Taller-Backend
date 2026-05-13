from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, Enum as SAEnum, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import InventoryMovementType
from app.core.dt import utc_now
from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.company import Company
    from app.db.models.service_order import ServiceOrder
    from app.db.models.supplier import Supplier
    from app.db.models.user import User


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    __table_args__ = (
        UniqueConstraint("company_id", "sku", name="uq_inventory_company_sku"),
        Index("ix_inventory_items_company_id", "company_id"),
    )

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    item_type: Mapped[str | None] = mapped_column(String(80))
    sku: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(120))
    quantity_stock: Mapped[Any] = mapped_column(Numeric(14, 3), default=0)
    quantity_minimum: Mapped[Any] = mapped_column(Numeric(14, 3), default=0)
    unit_cost: Mapped[Any | None] = mapped_column(Numeric(12, 2))
    unit_price: Mapped[Any | None] = mapped_column(Numeric(12, 2))
    supplier_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"))
    photos_urls: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    barcode: Mapped[str | None] = mapped_column(String(120))
    weight: Mapped[Any | None] = mapped_column(Numeric(12, 3))
    dimensions_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )
    last_restocked_at: Mapped[datetime | None] = mapped_column(DateTime)

    company: Mapped["Company"] = relationship("Company", back_populates="inventory_items")
    supplier: Mapped["Supplier | None"] = relationship("Supplier", back_populates="inventory_items")
    movements: Mapped[list["InventoryMovement"]] = relationship(
        "InventoryMovement", back_populates="inventory_item", cascade="all, delete-orphan"
    )


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"
    __table_args__ = (
        Index("ix_inventory_movements_item_id", "inventory_item_id"),
        Index("ix_inventory_movements_service_order_id", "service_order_id"),
        Index("ix_inventory_movements_moved_at", "moved_at"),
        CheckConstraint(
            "movement_type != 'used_in_repair' OR service_order_id IS NOT NULL",
            name="ck_inventory_movements_used_in_repair_requires_order",
        ),
    )

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    inventory_item_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("inventory_items.id"), nullable=False)
    movement_type: Mapped[InventoryMovementType] = mapped_column(
        SAEnum(InventoryMovementType, values_callable=lambda x: [e.value for e in x], native_enum=False),
        nullable=False,
    )
    quantity_change: Mapped[Any] = mapped_column(Numeric(14, 3), nullable=False)
    service_order_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), ForeignKey("service_orders.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    moved_by_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    moved_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    inventory_item: Mapped["InventoryItem"] = relationship("InventoryItem", back_populates="movements")
    service_order: Mapped["ServiceOrder | None"] = relationship("ServiceOrder")
    moved_by: Mapped["User | None"] = relationship("User")
