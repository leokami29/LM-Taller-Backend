"""Row Level Security y tablas de plataforma/auditoría

Revision ID: 002_multi_tenant
Revises: 001_initial
Create Date: 2026-05-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "002_multi_tenant"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tenant_visible_sql(company_column: str) -> str:
    return f"""(
  COALESCE(current_setting('app.platform_access', true), '') = 'true'
  OR ({company_column} = NULLIF(current_setting('app.tenant_company_id', true), '')::uuid)
)"""


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if "platform_users" not in insp.get_table_names():
        op.create_table(
            "platform_users",
            sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("email", sa.String(255), nullable=False, unique=True),
            sa.Column("hashed_password", sa.String(255), nullable=False),
            sa.Column("full_name", sa.String(255), nullable=False),
            sa.Column("role", sa.String(32), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    if "audit_logs" not in insp.get_table_names():
        op.create_table(
            "audit_logs",
            sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("actor_type", sa.String(16), nullable=False),
            sa.Column("actor_id", sa.String(64), nullable=False),
            sa.Column("company_id", UUID(as_uuid=True), nullable=True),
            sa.Column("action", sa.String(120), nullable=False),
            sa.Column("resource_type", sa.String(80), nullable=True),
            sa.Column("resource_id", sa.String(64), nullable=True),
            sa.Column("metadata_json", JSONB(), nullable=False, server_default=text("'{}'::jsonb")),
            sa.Column("ip_address", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("detail", sa.Text(), nullable=True),
        )

    tables_direct = [
        "users",
        "customers",
        "equipment",
        "service_orders",
        "inventory_items",
        "suppliers",
        "pdf_documents",
    ]
    for t in tables_direct:
        op.execute(text(f'ALTER TABLE "{t}" ENABLE ROW LEVEL SECURITY'))
        op.execute(text(f'ALTER TABLE "{t}" FORCE ROW LEVEL SECURITY'))
        op.execute(text(f'DROP POLICY IF EXISTS rls_tenant_isolation ON "{t}"'))
        op.execute(
            text(
                f'CREATE POLICY rls_tenant_isolation ON "{t}" FOR ALL '
                f"USING ({_tenant_visible_sql('company_id')}) "
                f"WITH CHECK ({_tenant_visible_sql('company_id')})"
            )
        )

    op.execute(text('ALTER TABLE "companies" ENABLE ROW LEVEL SECURITY'))
    op.execute(text('ALTER TABLE "companies" FORCE ROW LEVEL SECURITY'))
    op.execute(text('DROP POLICY IF EXISTS rls_tenant_isolation ON "companies"'))
    op.execute(
        text(
            f'CREATE POLICY rls_tenant_isolation ON "companies" FOR ALL '
            f"USING ({_tenant_visible_sql('id')}) "
            f"WITH CHECK ({_tenant_visible_sql('id')})"
        )
    )

    op.execute(text('ALTER TABLE "service_order_timeline" ENABLE ROW LEVEL SECURITY'))
    op.execute(text('ALTER TABLE "service_order_timeline" FORCE ROW LEVEL SECURITY'))
    op.execute(text('DROP POLICY IF EXISTS rls_tenant_isolation ON "service_order_timeline"'))
    op.execute(
        text(
            """
            CREATE POLICY rls_tenant_isolation ON "service_order_timeline" FOR ALL
            USING (
              COALESCE(current_setting('app.platform_access', true), '') = 'true'
              OR EXISTS (
                SELECT 1 FROM service_orders so
                WHERE so.id = service_order_timeline.service_order_id
                  AND so.company_id = NULLIF(current_setting('app.tenant_company_id', true), '')::uuid
              )
            )
            WITH CHECK (
              COALESCE(current_setting('app.platform_access', true), '') = 'true'
              OR EXISTS (
                SELECT 1 FROM service_orders so
                WHERE so.id = service_order_timeline.service_order_id
                  AND so.company_id = NULLIF(current_setting('app.tenant_company_id', true), '')::uuid
              )
            )
            """
        )
    )

    op.execute(text('ALTER TABLE "inventory_movements" ENABLE ROW LEVEL SECURITY'))
    op.execute(text('ALTER TABLE "inventory_movements" FORCE ROW LEVEL SECURITY'))
    op.execute(text('DROP POLICY IF EXISTS rls_tenant_isolation ON "inventory_movements"'))
    op.execute(
        text(
            """
            CREATE POLICY rls_tenant_isolation ON "inventory_movements" FOR ALL
            USING (
              COALESCE(current_setting('app.platform_access', true), '') = 'true'
              OR EXISTS (
                SELECT 1 FROM inventory_items ii
                WHERE ii.id = inventory_movements.inventory_item_id
                  AND ii.company_id = NULLIF(current_setting('app.tenant_company_id', true), '')::uuid
              )
            )
            WITH CHECK (
              COALESCE(current_setting('app.platform_access', true), '') = 'true'
              OR EXISTS (
                SELECT 1 FROM inventory_items ii
                WHERE ii.id = inventory_movements.inventory_item_id
                  AND ii.company_id = NULLIF(current_setting('app.tenant_company_id', true), '')::uuid
              )
            )
            """
        )
    )


def downgrade() -> None:
    for t in [
        "inventory_movements",
        "service_order_timeline",
        "companies",
        "users",
        "customers",
        "equipment",
        "service_orders",
        "inventory_items",
        "suppliers",
        "pdf_documents",
    ]:
        op.execute(text(f'DROP POLICY IF EXISTS rls_tenant_isolation ON "{t}"'))
        op.execute(text(f'ALTER TABLE "{t}" NO FORCE ROW LEVEL SECURITY'))
        op.execute(text(f'ALTER TABLE "{t}" DISABLE ROW LEVEL SECURITY'))
