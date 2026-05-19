from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.dt import utc_now
from app.core.enums import PlatformRole, SubscriptionStatus
from app.db.catalog.base import CatalogBase


class TenantRouting(CatalogBase):
    """Una fila por taller: resolución company_id/slug → URL de Postgres del data plane."""

    __tablename__ = "tenant_routing"
    __table_args__ = (
        Index("ix_tenant_routing_slug", "slug"),
        Index("ix_tenant_routing_active", "is_active"),
    )

    company_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    database_url: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    read_replica_url_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    schema_version_last_ok: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Denormalizado para listados de plataforma sin abrir cada BD
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nit_rut: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(50), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    company_created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CatalogPlatformUser(CatalogBase):
    """Usuario de plataforma almacenado solo en el catálogo cuando USE_TENANT_DATABASE_ROUTING=true."""

    __tablename__ = "platform_users"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[PlatformRole] = mapped_column(
        SAEnum(PlatformRole, values_callable=lambda x: [e.value for e in x], native_enum=False),
        default=PlatformRole.SUPPORT_READONLY,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )


class CatalogAuditLog(CatalogBase):
    """Auditoría de acciones de plataforma cuando el routing usa catálogo (sin depender del tenant DB)."""

    __tablename__ = "catalog_audit_logs"
    __table_args__ = (Index("ix_catalog_audit_action_created", "action", "created_at"),)

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    company_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class FeatureCatalog(CatalogBase):
    __tablename__ = "feature_catalog"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="module")


class Plan(CatalogBase):
    __tablename__ = "plans"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)


class PlanEntitlement(CatalogBase):
    __tablename__ = "plan_entitlements"
    __table_args__ = (UniqueConstraint("plan_id", "feature_code", name="uq_plan_entitlement"),)

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    plan_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False)
    feature_code: Mapped[str] = mapped_column(String(64), ForeignKey("feature_catalog.code"), nullable=False)
    value_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class TenantInstallation(CatalogBase):
    """Puesto desktop activo por taller (catálogo)."""

    __tablename__ = "tenant_installations"
    __table_args__ = (
        Index("ix_tenant_installations_company", "company_id"),
        UniqueConstraint("company_id", "installation_id", name="uq_tenant_installation_machine"),
    )

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False)
    installation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    activated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Subscription(CatalogBase):
    __tablename__ = "subscriptions"
    __table_args__ = (Index("ix_subscriptions_company", "company_id"),)

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), unique=True, nullable=False)
    plan_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False)
    status: Mapped[SubscriptionStatus] = mapped_column(
        SAEnum(SubscriptionStatus, values_callable=lambda x: [e.value for e in x], native_enum=False),
        default=SubscriptionStatus.ACTIVE,
    )
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    provider: Mapped[str] = mapped_column(String(16), default="manual")
    provider_subscription_id: Mapped[str | None] = mapped_column(String(128))
    entitlements_override_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    billing_email: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
