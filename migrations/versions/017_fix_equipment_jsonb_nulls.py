"""fix equipment jsonb nulls

Revision ID: 017
Revises: 016_inventory_categories
Create Date: 2026-05-23
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016_inventory_categories"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE equipment SET image_urls = '[]'::jsonb WHERE image_urls IS NULL")
    op.execute("UPDATE equipment SET tags = '[]'::jsonb WHERE tags IS NULL")
    op.execute("UPDATE equipment SET custom_fields = '{}'::jsonb WHERE custom_fields IS NULL")


def downgrade() -> None:
    pass
