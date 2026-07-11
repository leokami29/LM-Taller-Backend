"""add sla_policies table

Revision ID: 021
Revises: 020
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "sla_policies" in insp.get_table_names():
        return

    op.create_table(
        "sla_policies",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("order_kind", sa.String(30), nullable=True),
        sa.Column("priority", sa.String(20), nullable=True),
        sa.Column("response_time_hours", sa.Integer(), nullable=True),
        sa.Column("resolution_time_hours", sa.Integer(), nullable=True),
        sa.Column("warning_threshold_hours", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sla_policies_company_kind_priority", "sla_policies", ["company_id", "order_kind", "priority"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "sla_policies" not in insp.get_table_names():
        return
    op.drop_index("ix_sla_policies_company_kind_priority", table_name="sla_policies")
    op.drop_table("sla_policies")
