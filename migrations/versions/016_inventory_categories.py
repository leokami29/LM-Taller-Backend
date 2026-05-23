"""add inventory_categories table

Revision ID: 016_inventory_categories
Revises: 015
Create Date: 2026-05-23
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "016_inventory_categories"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "inventory_categories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("color", sa.String(7), nullable=True, server_default="#3b82f6"),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_inventory_categories_company_id", "inventory_categories", ["company_id"])
    op.create_index("ix_inventory_categories_name", "inventory_categories", ["company_id", "name"])


def downgrade() -> None:
    op.drop_index("ix_inventory_categories_name", table_name="inventory_categories")
    op.drop_index("ix_inventory_categories_company_id", table_name="inventory_categories")
    op.drop_table("inventory_categories")
