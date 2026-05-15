"""Índices de búsqueda para clientes (identificación y RUT)

Revision ID: 009_customer_search_idx
Revises: 008_customer_rut_notes
Create Date: 2026-05-15
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

revision: str = "009_customer_search_idx"
down_revision: Union[str, None] = "008_customer_rut_notes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "customers" not in insp.get_table_names():
        return

    existing = {ix["name"] for ix in insp.get_indexes("customers")}
    if "ix_customers_company_identification" not in existing:
        op.create_index(
            "ix_customers_company_identification",
            "customers",
            ["company_id", "identification_number"],
            unique=False,
        )
    if "ix_customers_company_rut" not in existing:
        op.create_index(
            "ix_customers_company_rut",
            "customers",
            ["company_id", "rut"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "customers" not in insp.get_table_names():
        return
    existing = {ix["name"] for ix in insp.get_indexes("customers")}
    if "ix_customers_company_rut" in existing:
        op.drop_index("ix_customers_company_rut", table_name="customers")
    if "ix_customers_company_identification" in existing:
        op.drop_index("ix_customers_company_identification", table_name="customers")
