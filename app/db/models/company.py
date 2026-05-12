from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.customer import Customer
    from app.db.models.equipment import Equipment
    from app.db.models.inventory import InventoryItem
    from app.db.models.pdf_document import PDFDocument
    from app.db.models.service_order import ServiceOrder
    from app.db.models.supplier import Supplier
    from app.db.models.user import User


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    nit_rut: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    logo_url: Mapped[str | None] = mapped_column(String(500))
    country: Mapped[str] = mapped_column(String(50), default="Colombia")
    currency: Mapped[str] = mapped_column(String(10), default="COP")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    next_order_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    users: Mapped[list["User"]] = relationship("User", back_populates="company", foreign_keys="User.company_id")
    customers: Mapped[list["Customer"]] = relationship("Customer", back_populates="company")
    equipment_list: Mapped[list["Equipment"]] = relationship("Equipment", back_populates="company")
    service_orders: Mapped[list["ServiceOrder"]] = relationship("ServiceOrder", back_populates="company")
    inventory_items: Mapped[list["InventoryItem"]] = relationship("InventoryItem", back_populates="company")
    suppliers: Mapped[list["Supplier"]] = relationship("Supplier", back_populates="company")
    pdf_documents: Mapped[list["PDFDocument"]] = relationship("PDFDocument", back_populates="company")
