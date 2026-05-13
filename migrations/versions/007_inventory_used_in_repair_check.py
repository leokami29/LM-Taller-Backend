"""CHECK: used_in_repair exige orden de servicio

Revision ID: 007_used_in_repair_check
Revises: 006_cross_table_company
Create Date: 2026-05-13

Idempotente: bases ya alineadas con el modelo SQLAlchemy pueden tener el CHECK creado por create_all.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

revision: str = "007_used_in_repair_check"
down_revision: Union[str, None] = "006_cross_table_company"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CHECK_NAME = "ck_inventory_movements_used_in_repair_requires_order"
_TABLE = "inventory_movements"
_SQL = "movement_type != 'used_in_repair' OR service_order_id IS NOT NULL"


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if _TABLE not in insp.get_table_names():
        return
    names = {c["name"] for c in insp.get_check_constraints(_TABLE)}
    if _CHECK_NAME not in names:
        op.create_check_constraint(_CHECK_NAME, _TABLE, _SQL)


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if _TABLE not in insp.get_table_names():
        return
    names = {c["name"] for c in insp.get_check_constraints(_TABLE)}
    if _CHECK_NAME in names:
        op.drop_constraint(_CHECK_NAME, _TABLE, type_="check")
