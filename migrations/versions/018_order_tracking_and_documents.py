"""order tracking_code and pdf document format

Revision ID: 018
Revises: 017
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())
    so_cols = {c["name"] for c in insp.get_columns("service_orders")} if "service_orders" in tables else set()
    pdf_cols = {c["name"] for c in insp.get_columns("pdf_documents")} if "pdf_documents" in tables else set()

    if "order_tracking_sequences" not in tables:
        op.create_table(
            "order_tracking_sequences",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("company_id", sa.UUID(), nullable=False),
            sa.Column("next_value", sa.Integer(), nullable=False, server_default="1"),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("company_id", name="uq_order_tracking_sequences_company"),
        )

    if "tracking_code" not in so_cols:
        op.add_column("service_orders", sa.Column("tracking_code", sa.String(length=16), nullable=True))
        op.create_index(
            "ix_service_orders_tracking_code",
            "service_orders",
            ["company_id", "tracking_code"],
            unique=True,
        )

    if "document_format" not in pdf_cols:
        op.add_column(
            "pdf_documents",
            sa.Column("document_format", sa.String(length=16), nullable=False, server_default="a4"),
        )
        op.alter_column("pdf_documents", "document_format", server_default=None)


def downgrade() -> None:
    op.drop_column("pdf_documents", "document_format")
    op.drop_index("ix_service_orders_tracking_code", table_name="service_orders")
    op.drop_column("service_orders", "tracking_code")
    op.drop_table("order_tracking_sequences")
