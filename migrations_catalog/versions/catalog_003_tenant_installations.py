"""tenant_installations for desktop seat licensing."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "catalog_003"
down_revision = "catalog_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_installations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("installation_id", sa.String(128), nullable=False),
        sa.Column("hostname", sa.String(255), nullable=True),
        sa.Column("activated_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("company_id", "installation_id", name="uq_tenant_installation_machine"),
    )
    op.create_index("ix_tenant_installations_company", "tenant_installations", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_tenant_installations_company", table_name="tenant_installations")
    op.drop_table("tenant_installations")
