"""Índices multi-tenant, columnas updated_at y auditoría consultable

Revision ID: 003_schema_indexes
Revises: 002_multi_tenant
Create Date: 2026-05-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision: str = "003_schema_indexes"
down_revision: Union[str, None] = "002_multi_tenant"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_names(bind, table: str) -> set[str]:
    insp = inspect(bind)
    return {ix["name"] for ix in insp.get_indexes(table)}


def _column_names(bind, table: str) -> set[str]:
    insp = inspect(bind)
    return {c["name"] for c in insp.get_columns(table)}


def _create_index_if_missing(bind, name: str, table: str, columns: list[str]) -> None:
    if name in _index_names(bind, table):
        return
    cols_sql = ", ".join(f'"{c}"' for c in columns)
    op.execute(text(f'CREATE INDEX "{name}" ON "{table}" ({cols_sql})'))


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    # --- Columnas updated_at (compatibilidad con DB creadas antes del modelo) ---
    if "suppliers" in insp.get_table_names():
        cols = _column_names(bind, "suppliers")
        if "updated_at" not in cols:
            op.add_column(
                "suppliers",
                sa.Column("updated_at", sa.DateTime(), nullable=True),
            )
            op.execute(text("UPDATE suppliers SET updated_at = created_at WHERE updated_at IS NULL"))
            op.alter_column("suppliers", "updated_at", nullable=False)

    if "pdf_documents" in insp.get_table_names():
        cols = _column_names(bind, "pdf_documents")
        if "updated_at" not in cols:
            op.add_column(
                "pdf_documents",
                sa.Column("updated_at", sa.DateTime(), nullable=True),
            )
            op.execute(text("UPDATE pdf_documents SET updated_at = generated_at WHERE updated_at IS NULL"))
            op.alter_column("pdf_documents", "updated_at", nullable=False)

    # --- Índices (consultas por empresa y joins frecuentes) ---
    _create_index_if_missing(bind, "ix_users_company_id", "users", ["company_id"])
    _create_index_if_missing(bind, "ix_customers_company_id", "customers", ["company_id"])
    _create_index_if_missing(bind, "ix_equipment_company_id", "equipment", ["company_id"])
    _create_index_if_missing(
        bind,
        "ix_service_orders_company_status_created",
        "service_orders",
        ["company_id", "status", "created_at"],
    )
    _create_index_if_missing(bind, "ix_service_orders_equipment_id", "service_orders", ["equipment_id"])
    _create_index_if_missing(
        bind, "ix_service_orders_current_customer_id", "service_orders", ["current_customer_id"]
    )
    _create_index_if_missing(bind, "ix_service_orders_assigned_to_id", "service_orders", ["assigned_to_id"])
    _create_index_if_missing(
        bind, "ix_service_order_timeline_order_id", "service_order_timeline", ["service_order_id"]
    )
    _create_index_if_missing(bind, "ix_inventory_items_company_id", "inventory_items", ["company_id"])
    _create_index_if_missing(
        bind, "ix_inventory_movements_item_id", "inventory_movements", ["inventory_item_id"]
    )
    _create_index_if_missing(
        bind,
        "ix_inventory_movements_service_order_id",
        "inventory_movements",
        ["service_order_id"],
    )
    _create_index_if_missing(bind, "ix_inventory_movements_moved_at", "inventory_movements", ["moved_at"])
    _create_index_if_missing(bind, "ix_suppliers_company_id", "suppliers", ["company_id"])
    _create_index_if_missing(bind, "ix_pdf_documents_company_id", "pdf_documents", ["company_id"])
    _create_index_if_missing(
        bind, "ix_pdf_documents_service_order_id", "pdf_documents", ["service_order_id"]
    )

    if "audit_logs" in insp.get_table_names():
        _create_index_if_missing(
            bind, "ix_audit_logs_company_created", "audit_logs", ["company_id", "created_at"]
        )
        _create_index_if_missing(bind, "ix_audit_logs_action_created", "audit_logs", ["action", "created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    for name, table in [
        ("ix_audit_logs_action_created", "audit_logs"),
        ("ix_audit_logs_company_created", "audit_logs"),
        ("ix_pdf_documents_service_order_id", "pdf_documents"),
        ("ix_pdf_documents_company_id", "pdf_documents"),
        ("ix_suppliers_company_id", "suppliers"),
        ("ix_inventory_movements_moved_at", "inventory_movements"),
        ("ix_inventory_movements_service_order_id", "inventory_movements"),
        ("ix_inventory_movements_item_id", "inventory_movements"),
        ("ix_inventory_items_company_id", "inventory_items"),
        ("ix_service_order_timeline_order_id", "service_order_timeline"),
        ("ix_service_orders_assigned_to_id", "service_orders"),
        ("ix_service_orders_current_customer_id", "service_orders"),
        ("ix_service_orders_equipment_id", "service_orders"),
        ("ix_service_orders_company_status_created", "service_orders"),
        ("ix_equipment_company_id", "equipment"),
        ("ix_customers_company_id", "customers"),
        ("ix_users_company_id", "users"),
    ]:
        if table in insp.get_table_names() and name in _index_names(bind, table):
            op.drop_index(name, table_name=table)

    # No eliminamos updated_at en suppliers/pdf_documents: puede haber existido
    # desde el esquema ORM inicial; revertir solo índices mantiene datos coherentes.
