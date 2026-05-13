"""Líneas de costo normalizadas por orden de servicio

Revision ID: 004_cost_lines
Revises: 003_schema_indexes
Create Date: 2026-05-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text
from sqlalchemy.dialects.postgresql import UUID

revision: str = "004_cost_lines"
down_revision: Union[str, None] = "003_schema_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tenant_visible_sql(company_column: str) -> str:
    return f"""(
  COALESCE(current_setting('app.platform_access', true), '') = 'true'
  OR ({company_column} = NULLIF(current_setting('app.tenant_company_id', true), '')::uuid)
)"""


def _index_names(bind, table: str) -> set[str]:
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {ix["name"] for ix in insp.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if "service_order_cost_lines" not in insp.get_table_names():
        op.create_table(
            "service_order_cost_lines",
            sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
            sa.Column(
                "service_order_id",
                UUID(as_uuid=True),
                sa.ForeignKey("service_orders.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("category", sa.String(16), nullable=False),
            sa.Column("description", sa.String(255), nullable=True),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )

    idx = _index_names(bind, "service_order_cost_lines")
    if "ix_service_order_cost_lines_company_id" not in idx:
        op.create_index(
            "ix_service_order_cost_lines_company_id",
            "service_order_cost_lines",
            ["company_id"],
        )
    if "ix_service_order_cost_lines_order_id" not in idx:
        op.create_index(
            "ix_service_order_cost_lines_order_id",
            "service_order_cost_lines",
            ["service_order_id"],
        )

    # Idempotente: refuerza RLS aunque la tabla viniera de create_all sin políticas.
    op.execute(text('ALTER TABLE "service_order_cost_lines" ENABLE ROW LEVEL SECURITY'))
    op.execute(text('ALTER TABLE "service_order_cost_lines" FORCE ROW LEVEL SECURITY'))
    op.execute(text('DROP POLICY IF EXISTS rls_tenant_isolation ON "service_order_cost_lines"'))
    op.execute(
        text(
            f'CREATE POLICY rls_tenant_isolation ON "service_order_cost_lines" FOR ALL '
            f"USING ({_tenant_visible_sql('company_id')}) "
            f"WITH CHECK ({_tenant_visible_sql('company_id')})"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "service_order_cost_lines" not in insp.get_table_names():
        return

    op.execute(text('DROP POLICY IF EXISTS rls_tenant_isolation ON "service_order_cost_lines"'))
    op.execute(text('ALTER TABLE "service_order_cost_lines" NO FORCE ROW LEVEL SECURITY'))
    op.execute(text('ALTER TABLE "service_order_cost_lines" DISABLE ROW LEVEL SECURITY'))

    idx = _index_names(bind, "service_order_cost_lines")
    if "ix_service_order_cost_lines_order_id" in idx:
        op.drop_index("ix_service_order_cost_lines_order_id", table_name="service_order_cost_lines")
    if "ix_service_order_cost_lines_company_id" in idx:
        op.drop_index("ix_service_order_cost_lines_company_id", table_name="service_order_cost_lines")

    op.drop_table("service_order_cost_lines")
