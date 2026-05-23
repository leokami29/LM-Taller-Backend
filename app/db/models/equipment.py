from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.dt import utc_now
from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.company import Company
    from app.db.models.customer import Customer
    from app.db.models.supplier import Supplier
    from app.db.models.service_order import ServiceOrder


class Equipment(Base):
    __tablename__ = "equipment"
    __table_args__ = (
        UniqueConstraint("company_id", "serial_number", name="uq_equipment_company_serial"),
        UniqueConstraint("company_id", "barcode", name="uq_equipment_company_barcode"),
        Index("ix_equipment_company_id", "company_id"),
        Index("ix_equipment_category", "company_id", "category"),
        Index("ix_equipment_status", "company_id", "status"),
        Index("ix_equipment_barcode", "company_id", "barcode"),
        Index("ix_equipment_supplier_id", "supplier_id"),
        Index("ix_equipment_parent_id", "parent_equipment_id"),
    )

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    serial_number: Mapped[str] = mapped_column(String(120), nullable=False)

    # Classification
    equipment_type: Mapped[str | None] = mapped_column(String(120))
    category: Mapped[str | None] = mapped_column(String(80))
    subcategory: Mapped[str | None] = mapped_column(String(80))

    # Identification
    brand: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120))
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    manufacturer_part_number: Mapped[str | None] = mapped_column(String(120))
    imei: Mapped[str | None] = mapped_column(String(32))
    color: Mapped[str | None] = mapped_column(String(64))
    barcode: Mapped[str | None] = mapped_column(String(64))

    # Ownership & lifecycle
    original_owner_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"))
    status: Mapped[str | None] = mapped_column(String(20), default="available")
    location: Mapped[str | None] = mapped_column(String(120))
    parent_equipment_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), ForeignKey("equipment.id"))

    # Procurement
    supplier_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"))
    purchase_date: Mapped[date | None] = mapped_column(Date)
    purchase_price: Mapped[Any | None] = mapped_column(Numeric(12, 2))

    # Warranty
    warranty_start: Mapped[date | None] = mapped_column(Date)
    warranty_end: Mapped[date | None] = mapped_column(Date)
    warranty_provider: Mapped[str | None] = mapped_column(String(120))

    # Media & metadata
    photos_urls: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    image_urls: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    tags: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    custom_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    additional_notes: Mapped[str | None] = mapped_column(Text)

    # Timestamps
    first_received_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="equipment_list")
    original_owner: Mapped["Customer | None"] = relationship("Customer", foreign_keys=[original_owner_id])
    supplier: Mapped["Supplier | None"] = relationship("Supplier")
    parent_equipment: Mapped["Equipment | None"] = relationship(
        "Equipment", remote_side="Equipment.id", foreign_keys=[parent_equipment_id], back_populates="child_equipment"
    )
    child_equipment: Mapped[list["Equipment"]] = relationship(
        "Equipment", back_populates="parent_equipment", foreign_keys=[parent_equipment_id]
    )
    attributes: Mapped[list["EquipmentAttribute"]] = relationship(
        "EquipmentAttribute", back_populates="equipment", cascade="all, delete-orphan"
    )


class EquipmentAttribute(Base):
    __tablename__ = "equipment_attributes"
    __table_args__ = (
        Index("ix_eq_attr_equipment_key", "equipment_id", "key"),
    )

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    equipment_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True), ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(20), default="text")

    equipment: Mapped["Equipment"] = relationship("Equipment", back_populates="attributes")
