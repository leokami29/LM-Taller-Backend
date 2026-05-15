"""Planes, features y suscripciones en catálogo

Revision ID: catalog_002
Revises: catalog_001
Create Date: 2026-05-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "catalog_002"
down_revision: Union[str, None] = "catalog_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feature_catalog",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=16), server_default="module", nullable=False),
        sa.PrimaryKeyConstraint("code"),
    )
    op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_public", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_plans_code"),
    )
    op.create_table(
        "plan_entitlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature_code", sa.String(length=64), nullable=False),
        sa.Column("value_json", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(["feature_code"], ["feature_catalog.code"]),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "feature_code", name="uq_plan_entitlement"),
    )
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("current_period_end", sa.DateTime(), nullable=True),
        sa.Column("provider", sa.String(length=16), server_default="manual", nullable=False),
        sa.Column("provider_subscription_id", sa.String(length=128), nullable=True),
        sa.Column(
            "entitlements_override_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("billing_email", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", name="uq_subscriptions_company"),
    )
    op.create_index("ix_subscriptions_company", "subscriptions", ["company_id"], unique=False)

    features = [
        ("core", "Core", "module"),
        ("customers", "Clientes", "module"),
        ("equipment", "Equipos", "module"),
        ("orders", "Órdenes", "module"),
        ("inventory", "Inventario", "module"),
        ("analytics", "Analítica", "module"),
        ("admin_users", "Usuarios", "module"),
        ("documents", "Documentos", "module"),
        ("max_users", "Máx. usuarios", "limit"),
        ("max_orders_month", "Máx. órdenes/mes", "limit"),
        ("storage_mb", "Almacenamiento MB", "limit"),
    ]
    conn = op.get_bind()
    for code, name, kind in features:
        conn.execute(
            sa.text(
                "INSERT INTO feature_catalog (code, name, kind) VALUES (:c, :n, :k) "
                "ON CONFLICT (code) DO NOTHING"
            ),
            {"c": code, "n": name, "k": kind},
        )

    op.execute(
        sa.text(
            """
            INSERT INTO plans (id, code, name, is_public) VALUES
            ('a1000001-0000-4000-8000-000000000001', 'starter', 'Starter', true),
            ('a1000001-0000-4000-8000-000000000002', 'pro', 'Pro', true),
            ('a1000001-0000-4000-8000-000000000003', 'enterprise', 'Enterprise', true)
            ON CONFLICT DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_subscriptions_company", table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_table("plan_entitlements")
    op.drop_table("plans")
    op.drop_table("feature_catalog")
