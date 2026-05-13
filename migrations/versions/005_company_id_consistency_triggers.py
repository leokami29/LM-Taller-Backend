"""Triggers de coherencia multi-tenant (company_id en órdenes y líneas de costo)

Revision ID: 005_company_triggers
Revises: 004_cost_lines
Create Date: 2026-05-13

Garantiza en base de datos que:
- service_order_cost_lines.company_id coincide con la orden enlazada.
- service_orders.company_id coincide con equipment, clientes y usuarios referenciados.

Las funciones usan SECURITY DEFINER + search_path fijo para que las lecturas
de verificación no queden vacías por RLS del rol de sesión.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "005_company_triggers"
down_revision: Union[str, None] = "004_cost_lines"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        text("""
CREATE OR REPLACE FUNCTION fn_enforce_service_order_cost_line_company()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_company uuid;
BEGIN
  SELECT so.company_id INTO STRICT v_company
  FROM service_orders so
  WHERE so.id = NEW.service_order_id;

  IF NEW.company_id IS DISTINCT FROM v_company THEN
    RAISE EXCEPTION
      'service_order_cost_lines.company_id (%) no coincide con service_orders.company_id (%) para orden %',
      NEW.company_id, v_company, NEW.service_order_id
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;
""")
    )

    op.execute(
        text("""
DROP TRIGGER IF EXISTS trg_service_order_cost_lines_company_chk ON service_order_cost_lines;
""")
    )
    op.execute(
        text("""
CREATE TRIGGER trg_service_order_cost_lines_company_chk
BEFORE INSERT OR UPDATE ON service_order_cost_lines
FOR EACH ROW
EXECUTE FUNCTION fn_enforce_service_order_cost_line_company();
""")
    )

    op.execute(
        text("""
CREATE OR REPLACE FUNCTION fn_enforce_service_order_reference_company()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v uuid;
BEGIN
  SELECT e.company_id INTO STRICT v FROM equipment e WHERE e.id = NEW.equipment_id;
  IF v IS DISTINCT FROM NEW.company_id THEN
    RAISE EXCEPTION
      'equipment.company_id no coincide con service_orders.company_id (equipo %, empresa orden %)',
      NEW.equipment_id, NEW.company_id
      USING ERRCODE = '23514';
  END IF;

  SELECT c.company_id INTO STRICT v FROM customers c WHERE c.id = NEW.current_customer_id;
  IF v IS DISTINCT FROM NEW.company_id THEN
    RAISE EXCEPTION
      'current_customer_id pertenece a otra empresa que la orden'
      USING ERRCODE = '23514';
  END IF;

  IF NEW.original_owner_id IS NOT NULL THEN
    SELECT c.company_id INTO STRICT v FROM customers c WHERE c.id = NEW.original_owner_id;
    IF v IS DISTINCT FROM NEW.company_id THEN
      RAISE EXCEPTION
        'original_owner_id pertenece a otra empresa que la orden'
        USING ERRCODE = '23514';
    END IF;
  END IF;

  IF NEW.assigned_to_id IS NOT NULL THEN
    SELECT u.company_id INTO STRICT v FROM users u WHERE u.id = NEW.assigned_to_id;
    IF v IS DISTINCT FROM NEW.company_id THEN
      RAISE EXCEPTION
        'assigned_to_id pertenece a otra empresa que la orden'
        USING ERRCODE = '23514';
    END IF;
  END IF;

  IF NEW.created_by_id IS NOT NULL THEN
    SELECT u.company_id INTO STRICT v FROM users u WHERE u.id = NEW.created_by_id;
    IF v IS DISTINCT FROM NEW.company_id THEN
      RAISE EXCEPTION
        'created_by_id pertenece a otra empresa que la orden'
        USING ERRCODE = '23514';
    END IF;
  END IF;

  RETURN NEW;
END;
$$;
""")
    )

    op.execute(
        text("""
DROP TRIGGER IF EXISTS trg_service_orders_reference_company_chk ON service_orders;
""")
    )
    op.execute(
        text("""
CREATE TRIGGER trg_service_orders_reference_company_chk
BEFORE INSERT OR UPDATE OF company_id, equipment_id, current_customer_id, original_owner_id, assigned_to_id, created_by_id
ON service_orders
FOR EACH ROW
EXECUTE FUNCTION fn_enforce_service_order_reference_company();
""")
    )


def downgrade() -> None:
    op.execute(
        text("""
DROP TRIGGER IF EXISTS trg_service_orders_reference_company_chk ON service_orders;
""")
    )
    op.execute(text("DROP FUNCTION IF EXISTS fn_enforce_service_order_reference_company();"))

    op.execute(
        text("""
DROP TRIGGER IF EXISTS trg_service_order_cost_lines_company_chk ON service_order_cost_lines;
""")
    )
    op.execute(text("DROP FUNCTION IF EXISTS fn_enforce_service_order_cost_line_company();"))
