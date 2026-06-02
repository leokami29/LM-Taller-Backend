"""site extra fields, accessories_json, pdf revision/copy

Revision ID: 019
Revises: 018
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _col_exists(bind, table: str, column: str) -> bool:
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    # sites: phone, email, address_override
    if not _col_exists(bind, "sites", "phone"):
        op.add_column("sites", sa.Column("phone", sa.String(30), nullable=True))
    if not _col_exists(bind, "sites", "email"):
        op.add_column("sites", sa.Column("email", sa.String(255), nullable=True))
    if not _col_exists(bind, "sites", "address_override"):
        op.add_column("sites", sa.Column("address_override", sa.Text(), nullable=True))

    # service_orders: accessories_json
    if not _col_exists(bind, "service_orders", "accessories_json"):
        op.add_column(
            "service_orders",
            sa.Column("accessories_json", sa.dialects.postgresql.JSONB(), nullable=True),
        )

    # pdf_documents: revision, is_copy
    if not _col_exists(bind, "pdf_documents", "revision"):
        op.add_column(
            "pdf_documents",
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        )
        op.alter_column("pdf_documents", "revision", server_default=None)
    if not _col_exists(bind, "pdf_documents", "is_copy"):
        op.add_column(
            "pdf_documents",
            sa.Column("is_copy", sa.Boolean(), nullable=False, server_default="false"),
        )
        op.alter_column("pdf_documents", "is_copy", server_default=None)


def downgrade() -> None:
    op.drop_column("pdf_documents", "is_copy")
    op.drop_column("pdf_documents", "revision")
    op.drop_column("service_orders", "accessories_json")
    op.drop_column("sites", "address_override")
    op.drop_column("sites", "email")
    op.drop_column("sites", "phone")
