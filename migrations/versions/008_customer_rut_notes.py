"""Campos rut y notes (observaciones) en clientes

Revision ID: 008_customer_rut_notes
Revises: 007_used_in_repair_check
Create Date: 2026-05-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision: str = "008_customer_rut_notes"
down_revision: Union[str, None] = "007_used_in_repair_check"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "customers" not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns("customers")}
    if "rut" not in cols:
        op.add_column("customers", sa.Column("rut", sa.String(length=20), nullable=True))
    if "notes" not in cols:
        op.add_column("customers", sa.Column("notes", sa.Text(), nullable=True))
        op.execute(
            text(
                """
                UPDATE customers
                SET notes = NULLIF(TRIM(metadata_json->>'notes'), '')
                WHERE metadata_json ? 'notes'
                  AND NULLIF(TRIM(metadata_json->>'notes'), '') IS NOT NULL
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "customers" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("customers")}
    if "notes" in cols:
        op.drop_column("customers", "notes")
    if "rut" in cols:
        op.drop_column("customers", "rut")
