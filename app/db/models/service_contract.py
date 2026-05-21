from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.dt import utc_now
from app.core.enums import ContractKind
from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.company import Company
    from app.db.models.customer import Customer
    from app.db.models.rbac import Site
    from app.db.models.service_order import ServiceOrder


class ServiceContract(Base):
    """Contrato o póliza de servicio."""

    __tablename__ = "service_contracts"
    __table_args__ = (
        UniqueConstraint("company_id", "contract_number", name="uq_service_contracts_company_number"),
        Index("ix_service_contracts_company_customer", "company_id", "customer_id"),
    )

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    customer_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    contract_number: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    contract_kind: Mapped[ContractKind] = mapped_column(
        SAEnum(ContractKind, values_callable=lambda x: [e.value for e in x], native_enum=False),
        default=ContractKind.CUSTOM,
        nullable=False,
    )
    default_site_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("sites.id"), nullable=False)
    allowed_order_kinds: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    template_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    max_orders_per_month: Mapped[int | None] = mapped_column(Integer)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    company: Mapped["Company"] = relationship("Company")
    customer: Mapped["Customer"] = relationship("Customer")
    default_site: Mapped["Site"] = relationship("Site")
    service_orders: Mapped[list["ServiceOrder"]] = relationship("ServiceOrder", back_populates="service_contract")
