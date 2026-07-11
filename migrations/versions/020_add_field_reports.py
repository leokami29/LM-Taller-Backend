"""add field_reports table

Revision ID: 020
Revises: 019
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "field_reports" in insp.get_table_names():
        return

    op.create_table(
        "field_reports",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("site_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("sites.id"), nullable=True),
        sa.Column("order_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("service_orders.id"), nullable=True),
        sa.Column("technician_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("findings", sa.Text(), nullable=True),
        sa.Column("recommendations", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("photos_urls", sa.dialects.postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_field_reports_company_created", "field_reports", ["company_id", "created_at"])
    op.create_index("ix_field_reports_order_id", "field_reports", ["order_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "field_reports" not in insp.get_table_names():
        return
    op.drop_index("ix_field_reports_order_id", table_name="field_reports")
    op.drop_index("ix_field_reports_company_created", table_name="field_reports")
    op.drop_table("field_reports")
