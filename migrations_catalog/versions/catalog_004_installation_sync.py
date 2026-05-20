"""Add last_successful_sync_at to tenant_installations."""

from alembic import op
import sqlalchemy as sa

revision = "catalog_004"
down_revision = "catalog_003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenant_installations",
        sa.Column("last_successful_sync_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenant_installations", "last_successful_sync_at")
