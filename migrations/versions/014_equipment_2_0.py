"""Equipment 2.0: new columns, attributes table, suppliers FK

Revision ID: 014_equipment_2_0
Revises: 013_portal_contracts
Create Date: 2026-05-22
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision: str = "014_equipment_2_0"
down_revision: Union[str, None] = "013_portal_contracts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to equipment table
    op.add_column("equipment", sa.Column("category", sa.String(80), nullable=True))
    op.add_column("equipment", sa.Column("subcategory", sa.String(80), nullable=True))
    op.add_column("equipment", sa.Column("status", sa.String(20), nullable=True, server_default="available"))
    op.add_column("equipment", sa.Column("location", sa.String(120), nullable=True))
    op.add_column("equipment", sa.Column("barcode", sa.String(64), nullable=True))
    op.add_column("equipment", sa.Column("manufacturer", sa.String(120), nullable=True))
    op.add_column("equipment", sa.Column("manufacturer_part_number", sa.String(120), nullable=True))
    op.add_column("equipment", sa.Column("supplier_id", UUID(as_uuid=True), nullable=True))
    op.add_column("equipment", sa.Column("purchase_date", sa.Date(), nullable=True))
    op.add_column("equipment", sa.Column("purchase_price", sa.Numeric(12, 2), nullable=True))
    op.add_column("equipment", sa.Column("warranty_start", sa.Date(), nullable=True))
    op.add_column("equipment", sa.Column("warranty_end", sa.Date(), nullable=True))
    op.add_column("equipment", sa.Column("warranty_provider", sa.String(120), nullable=True))
    op.add_column("equipment", sa.Column("image_urls", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("equipment", sa.Column("tags", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("equipment", sa.Column("custom_fields", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("equipment", sa.Column("parent_equipment_id", UUID(as_uuid=True), nullable=True))

    # Constraints
    op.create_unique_constraint("uq_equipment_company_barcode", "equipment", ["company_id", "barcode"])
    op.create_foreign_key("fk_equipment_supplier_id", "equipment", "suppliers", ["supplier_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_equipment_parent_id", "equipment", "equipment", ["parent_equipment_id"], ["id"], ondelete="SET NULL")

    # Indexes
    op.create_index("ix_equipment_category", "equipment", ["company_id", "category"])
    op.create_index("ix_equipment_status", "equipment", ["company_id", "status"])
    op.create_index("ix_equipment_barcode", "equipment", ["company_id", "barcode"])
    op.create_index("ix_equipment_supplier_id", "equipment", ["supplier_id"])
    op.create_index("ix_equipment_parent_id", "equipment", ["parent_equipment_id"])

    # EquipmentAttributes table
    op.create_table(
        "equipment_attributes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("equipment_id", UUID(as_uuid=True), sa.ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("type", sa.String(20), nullable=False, server_default="text"),
    )
    op.create_index("ix_eq_attr_equipment_key", "equipment_attributes", ["equipment_id", "key"])


def downgrade() -> None:
    op.drop_table("equipment_attributes")
    op.drop_index("ix_equipment_parent_id", table_name="equipment")
    op.drop_index("ix_equipment_supplier_id", table_name="equipment")
    op.drop_index("ix_equipment_barcode", table_name="equipment")
    op.drop_index("ix_equipment_status", table_name="equipment")
    op.drop_index("ix_equipment_category", table_name="equipment")
    op.drop_constraint("fk_equipment_parent_id", "equipment", type_="foreignkey")
    op.drop_constraint("fk_equipment_supplier_id", "equipment", type_="foreignkey")
    op.drop_constraint("uq_equipment_company_barcode", "equipment", type_="unique")
    op.drop_column("equipment", "parent_equipment_id")
    op.drop_column("equipment", "custom_fields")
    op.drop_column("equipment", "tags")
    op.drop_column("equipment", "image_urls")
    op.drop_column("equipment", "warranty_provider")
    op.drop_column("equipment", "warranty_end")
    op.drop_column("equipment", "warranty_start")
    op.drop_column("equipment", "purchase_price")
    op.drop_column("equipment", "purchase_date")
    op.drop_column("equipment", "supplier_id")
    op.drop_column("equipment", "manufacturer_part_number")
    op.drop_column("equipment", "manufacturer")
    op.drop_column("equipment", "barcode")
    op.drop_column("equipment", "location")
    op.drop_column("equipment", "status")
    op.drop_column("equipment", "subcategory")
    op.drop_column("equipment", "category")
