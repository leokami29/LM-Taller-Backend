"""Campos de recepción en service_orders (ingreso de orden)

Revision ID: 011_service_order_intake
Revises: 010_rbac_multisite
Create Date: 2026-05-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "011_service_order_intake"
down_revision: Union[str, None] = "010_rbac_multisite"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "service_orders",
        sa.Column("site_id", UUID(as_uuid=True), sa.ForeignKey("sites.id"), nullable=True),
    )
    op.add_column(
        "service_orders",
        sa.Column("received_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "service_orders",
        sa.Column(
            "received_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "service_orders",
        sa.Column("customer_po_number", sa.String(64), nullable=True),
    )
    op.add_column(
        "service_orders",
        sa.Column("sales_area", sa.String(120), nullable=True),
    )
    op.add_column(
        "service_orders",
        sa.Column("device_condition_on_entry", sa.Text(), nullable=True),
    )
    op.create_index("ix_service_orders_site_id", "service_orders", ["site_id"])


def downgrade() -> None:
    op.drop_index("ix_service_orders_site_id", table_name="service_orders")
    op.drop_column("service_orders", "device_condition_on_entry")
    op.drop_column("service_orders", "sales_area")
    op.drop_column("service_orders", "customer_po_number")
    op.drop_column("service_orders", "received_by_id")
    op.drop_column("service_orders", "received_at")
    op.drop_column("service_orders", "site_id")
