"""RBAC multi-sede, planes en companies y tablas de workflow

Revision ID: 010_rbac_multisite
Revises: 009_customer_search_idx
Create Date: 2026-05-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "010_rbac_multisite"
down_revision: Union[str, None] = "009_customer_search_idx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tenant_visible_sql(company_column: str) -> str:
    return f"""(
  COALESCE(current_setting('app.platform_access', true), '') = 'true'
  OR ({company_column} = NULLIF(current_setting('app.tenant_company_id', true), '')::uuid)
)"""


def _enable_rls(table: str, company_column: str = "company_id") -> None:
    op.execute(text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(text(f'DROP POLICY IF EXISTS rls_tenant_isolation ON "{table}"'))
    op.execute(
        text(
            f'CREATE POLICY rls_tenant_isolation ON "{table}" FOR ALL '
            f"USING ({_tenant_visible_sql(company_column)}) "
            f"WITH CHECK ({_tenant_visible_sql(company_column)})"
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if "companies" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("companies")}
        if "plan" not in cols:
            op.add_column("companies", sa.Column("plan", sa.String(32), server_default="starter", nullable=False))
        if "subscription_status" not in cols:
            op.add_column(
                "companies",
                sa.Column("subscription_status", sa.String(32), server_default="active", nullable=False),
            )
        if "active_users_limit" not in cols:
            op.add_column("companies", sa.Column("active_users_limit", sa.Integer(), nullable=True))
        if "billing_email" not in cols:
            op.add_column("companies", sa.Column("billing_email", sa.String(255), nullable=True))

    if "audit_logs" in insp.get_table_names():
        acols = {c["name"] for c in insp.get_columns("audit_logs")}
        if "user_id" not in acols:
            op.add_column("audit_logs", sa.Column("user_id", UUID(as_uuid=True), nullable=True))
        if "site_id" not in acols:
            op.add_column("audit_logs", sa.Column("site_id", UUID(as_uuid=True), nullable=True))
        if "user_agent" not in acols:
            op.add_column("audit_logs", sa.Column("user_agent", sa.String(512), nullable=True))
        existing_audit_idx = {ix["name"] for ix in insp.get_indexes("audit_logs")}
        if "ix_audit_logs_user_id" not in existing_audit_idx:
            op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])

    if "sites" not in insp.get_table_names():
        op.create_table(
            "sites",
            sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("location", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("company_id", "name", name="uq_sites_company_name"),
        )
        op.create_index("ix_sites_company_id", "sites", ["company_id"])
        _enable_rls("sites")

    if "user_site_roles" not in insp.get_table_names():
        op.create_table(
            "user_site_roles",
            sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
            sa.Column("site_id", UUID(as_uuid=True), sa.ForeignKey("sites.id"), nullable=True),
            sa.Column("role", sa.String(32), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_user_site_roles_user_company", "user_site_roles", ["user_id", "company_id"])
        op.create_index("ix_user_site_roles_company_site", "user_site_roles", ["company_id", "site_id"])
        op.execute(
            text(
                "CREATE UNIQUE INDEX uq_user_site_roles_all_sites "
                "ON user_site_roles (user_id, company_id) WHERE site_id IS NULL"
            )
        )
        op.execute(
            text(
                "CREATE UNIQUE INDEX uq_user_site_roles_per_site "
                "ON user_site_roles (user_id, company_id, site_id) WHERE site_id IS NOT NULL"
            )
        )
        _enable_rls("user_site_roles")

    if "role_change_requests" not in insp.get_table_names():
        op.create_table(
            "role_change_requests",
            sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
            sa.Column("site_id", UUID(as_uuid=True), sa.ForeignKey("sites.id"), nullable=True),
            sa.Column("requested_role", sa.String(32), nullable=False),
            sa.Column("requested_by_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("approved_by_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("status", sa.String(32), server_default="pending", nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index(
            "ix_role_change_requests_company_status",
            "role_change_requests",
            ["company_id", "status"],
        )
        _enable_rls("role_change_requests")

    if "temporary_permissions" not in insp.get_table_names():
        op.create_table(
            "temporary_permissions",
            sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
            sa.Column("site_id", UUID(as_uuid=True), sa.ForeignKey("sites.id"), nullable=True),
            sa.Column("permission", sa.String(80), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("granted_by_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index(
            "ix_temporary_permissions_user_expires",
            "temporary_permissions",
            ["user_id", "expires_at"],
        )
        _enable_rls("temporary_permissions")

    # Backfill: sede Principal + user_site_roles desde users.role
    if "sites" in {t for t in insp.get_table_names()} or "sites" in inspect(bind).get_table_names():
        op.execute(
            text(
                """
                INSERT INTO sites (id, company_id, name, location, is_active, created_at, updated_at)
                SELECT gen_random_uuid(), c.id, 'Principal', c.address, true, NOW(), NOW()
                FROM companies c
                WHERE NOT EXISTS (
                    SELECT 1 FROM sites s WHERE s.company_id = c.id AND s.name = 'Principal'
                )
                """
            )
        )
        op.execute(
            text(
                """
                INSERT INTO user_site_roles (id, user_id, company_id, site_id, role, is_active, created_at, updated_at)
                SELECT gen_random_uuid(), u.id, u.company_id,
                    CASE WHEN u.role = 'admin' THEN NULL ELSE s.id END,
                    u.role, true, NOW(), NOW()
                FROM users u
                JOIN sites s ON s.company_id = u.company_id AND s.name = 'Principal'
                WHERE NOT EXISTS (
                    SELECT 1 FROM user_site_roles usr
                    WHERE usr.user_id = u.id AND usr.company_id = u.company_id
                      AND (
                        (usr.site_id IS NULL AND u.role = 'admin')
                        OR usr.site_id = s.id
                      )
                )
                """
            )
        )
        op.execute(
            text(
                """
                UPDATE companies SET plan = 'starter', subscription_status = 'active', active_users_limit = 5
                WHERE active_users_limit IS NULL
                """
            )
        )


def downgrade() -> None:
    op.execute(text("DROP INDEX IF EXISTS uq_user_site_roles_per_site"))
    op.execute(text("DROP INDEX IF EXISTS uq_user_site_roles_all_sites"))
    for t in ("temporary_permissions", "role_change_requests", "user_site_roles", "sites"):
        op.execute(text(f'DROP POLICY IF EXISTS rls_tenant_isolation ON "{t}"'))
        op.drop_table(t)
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_column("audit_logs", "user_agent")
    op.drop_column("audit_logs", "site_id")
    op.drop_column("audit_logs", "user_id")
    op.drop_column("companies", "billing_email")
    op.drop_column("companies", "active_users_limit")
    op.drop_column("companies", "subscription_status")
    op.drop_column("companies", "plan")
