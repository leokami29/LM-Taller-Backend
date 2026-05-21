"""Tipos de orden, códigos de sede y secuencias por sede+tipo

Revision ID: 012_order_kinds_numbering
Revises: 011_service_order_intake
Create Date: 2026-05-18
"""

from __future__ import annotations

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "012_order_kinds_numbering"
down_revision: Union[str, None] = "011_service_order_intake"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ORDER_KIND_ENUM = sa.Enum(
    "workshop_intake",
    "workshop_intake_contract",
    "field_service",
    "field_service_contract",
    name="serviceorderkind",
    native_enum=False,
)


def _derive_site_code(name: str, existing: set[str]) -> str:
    words = re.findall(r"[A-Za-z0-9]+", name or "")
    if not words:
        base = "SITE"
    elif len(words) == 1:
        base = words[0][:8].upper()
    else:
        base = "".join(w[0] for w in words[:4]).upper()
        if len(base) < 2:
            base = words[0][:8].upper()
    base = re.sub(r"[^A-Z0-9]", "", base)[:8] or "SITE"
    code = base
    n = 1
    while code in existing:
        suffix = str(n)
        code = f"{base[: max(2, 8 - len(suffix))]}{suffix}"[:8]
        n += 1
    return code


def upgrade() -> None:
    ORDER_KIND_ENUM.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "service_contracts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("contract_number", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "contract_number", name="uq_service_contracts_company_number"),
    )
    op.create_index(
        "ix_service_contracts_company_customer",
        "service_contracts",
        ["company_id", "customer_id"],
    )

    op.add_column("sites", sa.Column("code", sa.String(8), nullable=True))
    conn = op.get_bind()
    sites = conn.execute(sa.text("SELECT id, company_id, name FROM sites ORDER BY company_id, name")).fetchall()
    by_company: dict = {}
    for row in sites:
        company_id = str(row.company_id)
        used = by_company.setdefault(company_id, set())
        code = _derive_site_code(row.name, used)
        used.add(code)
        conn.execute(
            sa.text("UPDATE sites SET code = :code WHERE id = :id"),
            {"code": code, "id": row.id},
        )
    op.alter_column("sites", "code", nullable=False)
    op.create_unique_constraint("uq_sites_company_code", "sites", ["company_id", "code"])

    op.add_column(
        "service_orders",
        sa.Column("order_kind", ORDER_KIND_ENUM, nullable=False, server_default="workshop_intake"),
    )
    op.add_column(
        "service_orders",
        sa.Column("service_contract_id", UUID(as_uuid=True), sa.ForeignKey("service_contracts.id"), nullable=True),
    )
    op.add_column(
        "service_orders",
        sa.Column("parent_order_id", UUID(as_uuid=True), sa.ForeignKey("service_orders.id"), nullable=True),
    )
    op.create_index("ix_service_orders_company_order_kind", "service_orders", ["company_id", "order_kind"])
    op.create_index("ix_service_orders_service_contract_id", "service_orders", ["service_contract_id"])
    op.create_index("ix_service_orders_parent_order_id", "service_orders", ["parent_order_id"])

    op.create_table(
        "order_number_sequences",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("site_id", UUID(as_uuid=True), sa.ForeignKey("sites.id"), nullable=False),
        sa.Column("order_kind", ORDER_KIND_ENUM, nullable=False),
        sa.Column("next_value", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint(
            "company_id",
            "site_id",
            "order_kind",
            name="uq_order_number_sequences_company_site_kind",
        ),
    )


def downgrade() -> None:
    op.drop_table("order_number_sequences")
    op.drop_index("ix_service_orders_parent_order_id", table_name="service_orders")
    op.drop_index("ix_service_orders_service_contract_id", table_name="service_orders")
    op.drop_index("ix_service_orders_company_order_kind", table_name="service_orders")
    op.drop_column("service_orders", "parent_order_id")
    op.drop_column("service_orders", "service_contract_id")
    op.drop_column("service_orders", "order_kind")
    op.drop_constraint("uq_sites_company_code", "sites", type_="unique")
    op.drop_column("sites", "code")
    op.drop_index("ix_service_contracts_company_customer", table_name="service_contracts")
    op.drop_table("service_contracts")
    ORDER_KIND_ENUM.drop(op.get_bind(), checkfirst=True)
