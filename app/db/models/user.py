from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.dt import utc_now
from app.core.enums import UserRole
from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.company import Company
    from app.db.models.rbac import UserSiteRole
    from app.db.models.service_order import ServiceOrder


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("company_id", "email", name="uq_users_company_email"),
        Index("ix_users_company_id", "company_id"),
    )

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, values_callable=lambda x: [e.value for e in x], native_enum=False),
        default=UserRole.RECEPTION,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    last_login: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )
    created_by_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))

    company: Mapped["Company"] = relationship("Company", back_populates="users", foreign_keys=[company_id])
    creator: Mapped["User | None"] = relationship("User", remote_side="User.id", foreign_keys=[created_by_id])

    assigned_orders: Mapped[list["ServiceOrder"]] = relationship(
        "ServiceOrder",
        foreign_keys="ServiceOrder.assigned_to_id",
        back_populates="assigned_technician",
    )
    orders_created: Mapped[list["ServiceOrder"]] = relationship(
        "ServiceOrder",
        foreign_keys="ServiceOrder.created_by_id",
        back_populates="created_by",
    )
    site_roles: Mapped[list["UserSiteRole"]] = relationship(
        "UserSiteRole",
        back_populates="user",
        foreign_keys="UserSiteRole.user_id",
    )
