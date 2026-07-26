"""Widen service_orders.tracking_code for non-enumerable tokens.

Revision ID: 022
Revises: 021
Create Date: 2026-07-26
"""

from alembic import op
import sqlalchemy as sa

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "service_orders",
        "tracking_code",
        existing_type=sa.String(length=16),
        type_=sa.String(length=40),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "service_orders",
        "tracking_code",
        existing_type=sa.String(length=40),
        type_=sa.String(length=16),
        existing_nullable=True,
    )
