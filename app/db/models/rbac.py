"""RBAC multi-sede: sedes, roles por sede, cambios de rol y permisos temporales."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.dt import utc_now
from app.core.enums import RoleChangeStatus, UserRole
from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.company import Company
    from app.db.models.user import User


class Site(Base):
    __tablename__ = "sites"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_sites_company_name"),
        UniqueConstraint("company_id", "code", name="uq_sites_company_code"),
        Index("ix_sites_company_id", "company_id"),
    )

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(8), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    location: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    company: Mapped["Company"] = relationship("Company", back_populates="sites")
    user_roles: Mapped[list["UserSiteRole"]] = relationship("UserSiteRole", back_populates="site")


class UserSiteRole(Base):
    __tablename__ = "user_site_roles"
    __table_args__ = (
        Index("ix_user_site_roles_user_company", "user_id", "company_id"),
        Index("ix_user_site_roles_company_site", "company_id", "site_id"),
    )

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    company_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    site_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sites.id"), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, values_callable=lambda x: [e.value for e in x], native_enum=False),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    user: Mapped["User"] = relationship("User", back_populates="site_roles", foreign_keys=[user_id])
    company: Mapped["Company"] = relationship("Company", back_populates="user_site_roles")
    site: Mapped["Site | None"] = relationship("Site", back_populates="user_roles")


class RoleChangeRequest(Base):
    __tablename__ = "role_change_requests"
    __table_args__ = (Index("ix_role_change_requests_company_status", "company_id", "status"),)

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    company_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    site_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sites.id"), nullable=True)
    requested_role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, values_callable=lambda x: [e.value for e in x], native_enum=False),
        nullable=False,
    )
    requested_by_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    approved_by_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status: Mapped[RoleChangeStatus] = mapped_column(
        SAEnum(RoleChangeStatus, values_callable=lambda x: [e.value for e in x], native_enum=False),
        default=RoleChangeStatus.PENDING,
    )
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    requested_by: Mapped["User"] = relationship("User", foreign_keys=[requested_by_id])
    approved_by: Mapped["User | None"] = relationship("User", foreign_keys=[approved_by_id])


class TemporaryPermission(Base):
    __tablename__ = "temporary_permissions"
    __table_args__ = (Index("ix_temporary_permissions_user_expires", "user_id", "expires_at"),)

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    company_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    site_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sites.id"), nullable=True)
    permission: Mapped[str] = mapped_column(String(80), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    granted_by_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    granted_by: Mapped["User"] = relationship("User", foreign_keys=[granted_by_id])
