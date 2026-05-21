"""Contratos ampliados, portal cliente y respuestas de plantilla

Revision ID: 013_portal_contracts
Revises: 012_order_kinds_numbering
Create Date: 2026-05-21
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "013_portal_contracts"
down_revision: Union[str, None] = "012_order_kinds_numbering"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONTRACT_KIND_ENUM = sa.Enum(
    "maintenance",
    "warranty",
    "field_sla",
    "custom",
    name="contractkind",
    native_enum=False,
)


def upgrade() -> None:
    CONTRACT_KIND_ENUM.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "service_contracts",
        sa.Column(
            "contract_kind",
            CONTRACT_KIND_ENUM,
            nullable=False,
            server_default="custom",
        ),
    )
    op.add_column(
        "service_contracts",
        sa.Column("default_site_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "service_contracts",
        sa.Column("allowed_order_kinds", JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "service_contracts",
        sa.Column("template_json", JSONB(), nullable=False, server_default="{}"),
    )
    op.add_column("service_contracts", sa.Column("max_orders_per_month", sa.Integer(), nullable=True))

    conn = op.get_bind()
    sites = conn.execute(sa.text("SELECT id, company_id FROM sites")).fetchall()
    site_by_company = {str(r.company_id): r.id for r in sites}
    contracts = conn.execute(sa.text("SELECT id, company_id FROM service_contracts")).fetchall()
    for row in contracts:
        site_id = site_by_company.get(str(row.company_id))
        if site_id:
            conn.execute(
                sa.text(
                    "UPDATE service_contracts SET default_site_id = :sid, "
                    "allowed_order_kinds = :kinds WHERE id = :id"
                ),
                {
                    "sid": site_id,
                    "kinds": '["workshop_intake_contract"]',
                    "id": row.id,
                },
            )
    op.alter_column("service_contracts", "default_site_id", nullable=False)
    op.create_foreign_key(
        "fk_service_contracts_default_site",
        "service_contracts",
        "sites",
        ["default_site_id"],
        ["id"],
    )

    op.add_column("service_orders", sa.Column("portal_submitted_json", JSONB(), nullable=True))

    op.create_table(
        "customer_portal_users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("last_login", sa.DateTime(), nullable=True),
        sa.Column("invited_by_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "email", name="uq_customer_portal_users_company_email"),
    )
    op.create_index(
        "ix_customer_portal_users_company_customer",
        "customer_portal_users",
        ["company_id", "customer_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_customer_portal_users_company_customer", table_name="customer_portal_users")
    op.drop_table("customer_portal_users")
    op.drop_column("service_orders", "portal_submitted_json")
    op.drop_constraint("fk_service_contracts_default_site", "service_contracts", type_="foreignkey")
    op.drop_column("service_contracts", "max_orders_per_month")
    op.drop_column("service_contracts", "template_json")
    op.drop_column("service_contracts", "allowed_order_kinds")
    op.drop_column("service_contracts", "default_site_id")
    op.drop_column("service_contracts", "contract_kind")
    CONTRACT_KIND_ENUM.drop(op.get_bind(), checkfirst=True)
