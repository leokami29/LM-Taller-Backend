"""Coherencia multi-tenant en inventario, PDFs y timeline de órdenes

Revision ID: 006_cross_table_company
Revises: 005_company_triggers
Create Date: 2026-05-13

Casos de uso cubiertos (y qué queda fuera a propósito):

1) inventory_movements
   - Movimiento **sin** orden (compra, ajuste, daño, etc.): `service_order_id` NULL → no se exige orden;
     el ítem ya ancla el tenant vía RLS sobre `inventory_items`.
   - Movimiento **con** orden (p. ej. USED_IN_REPAIR): la orden debe ser de la **misma empresa**
     que el `inventory_item` (evita consumo ficticio cruzando tenants).
   - `moved_by_id` opcional: si viene informado, el usuario debe ser de la misma empresa que el ítem
     (coherencia de auditoría; no sustituye permisos en API).

   **used_in_repair y orden:** la regla de negocio “debe existir orden” se aplica en API/servicio y en el
   CHECK de la migración `007_used_in_repair_check` (además de la validación en `apply_stock_change`).

2) pdf_documents
   - Documento **sin** orden: solo `company_id` (presupuesto global, etc.).
   - Con `service_order_id`: `company_id` del PDF = `company_id` de la orden.
   - `generated_by_id` opcional: si existe, usuario misma empresa que el documento.

3) service_order_timeline
   - `changed_by_id` opcional: si existe, usuario misma empresa que la orden del timeline.

Funciones SECURITY DEFINER + search_path fijo (mismo criterio que 005) para lecturas bajo RLS.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "006_cross_table_company"
down_revision: Union[str, None] = "005_company_triggers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        text("""
CREATE OR REPLACE FUNCTION fn_enforce_inventory_movement_tenant_links()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_item_company uuid;
  v_order_company uuid;
  v_user_company uuid;
BEGIN
  SELECT ii.company_id INTO STRICT v_item_company
  FROM inventory_items ii
  WHERE ii.id = NEW.inventory_item_id;

  IF NEW.service_order_id IS NOT NULL THEN
    SELECT so.company_id INTO STRICT v_order_company
    FROM service_orders so
    WHERE so.id = NEW.service_order_id;
    IF v_order_company IS DISTINCT FROM v_item_company THEN
      RAISE EXCEPTION
        'inventory_movements: la orden % no es de la misma empresa que el ítem de inventario %',
        NEW.service_order_id, NEW.inventory_item_id
        USING ERRCODE = '23514';
    END IF;
  END IF;

  IF NEW.moved_by_id IS NOT NULL THEN
    SELECT u.company_id INTO STRICT v_user_company
    FROM users u
    WHERE u.id = NEW.moved_by_id;
    IF v_user_company IS DISTINCT FROM v_item_company THEN
      RAISE EXCEPTION
        'inventory_movements: moved_by_id no pertenece a la empresa del ítem'
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
DROP TRIGGER IF EXISTS trg_inventory_movements_tenant_links ON inventory_movements;
""")
    )
    op.execute(
        text("""
CREATE TRIGGER trg_inventory_movements_tenant_links
BEFORE INSERT OR UPDATE OF inventory_item_id, service_order_id, moved_by_id
ON inventory_movements
FOR EACH ROW
EXECUTE FUNCTION fn_enforce_inventory_movement_tenant_links();
""")
    )

    op.execute(
        text("""
CREATE OR REPLACE FUNCTION fn_enforce_pdf_document_order_tenant()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_order_company uuid;
  v_user_company uuid;
BEGIN
  IF NEW.service_order_id IS NOT NULL THEN
    SELECT so.company_id INTO STRICT v_order_company
    FROM service_orders so
    WHERE so.id = NEW.service_order_id;
    IF v_order_company IS DISTINCT FROM NEW.company_id THEN
      RAISE EXCEPTION
        'pdf_documents: company_id no coincide con la empresa de la orden %',
        NEW.service_order_id
        USING ERRCODE = '23514';
    END IF;
  END IF;

  IF NEW.generated_by_id IS NOT NULL THEN
    SELECT u.company_id INTO STRICT v_user_company
    FROM users u
    WHERE u.id = NEW.generated_by_id;
    IF v_user_company IS DISTINCT FROM NEW.company_id THEN
      RAISE EXCEPTION
        'pdf_documents: generated_by_id no pertenece a la empresa del documento'
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
DROP TRIGGER IF EXISTS trg_pdf_documents_order_tenant ON pdf_documents;
""")
    )
    op.execute(
        text("""
CREATE TRIGGER trg_pdf_documents_order_tenant
BEFORE INSERT OR UPDATE OF company_id, service_order_id, generated_by_id
ON pdf_documents
FOR EACH ROW
EXECUTE FUNCTION fn_enforce_pdf_document_order_tenant();
""")
    )

    op.execute(
        text("""
CREATE OR REPLACE FUNCTION fn_enforce_service_order_timeline_actor_tenant()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_order_company uuid;
  v_user_company uuid;
BEGIN
  SELECT so.company_id INTO STRICT v_order_company
  FROM service_orders so
  WHERE so.id = NEW.service_order_id;

  IF NEW.changed_by_id IS NOT NULL THEN
    SELECT u.company_id INTO STRICT v_user_company
    FROM users u
    WHERE u.id = NEW.changed_by_id;
    IF v_user_company IS DISTINCT FROM v_order_company THEN
      RAISE EXCEPTION
        'service_order_timeline: changed_by_id no pertenece a la empresa de la orden'
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
DROP TRIGGER IF EXISTS trg_service_order_timeline_actor_tenant ON service_order_timeline;
""")
    )
    op.execute(
        text("""
CREATE TRIGGER trg_service_order_timeline_actor_tenant
BEFORE INSERT OR UPDATE OF service_order_id, changed_by_id
ON service_order_timeline
FOR EACH ROW
EXECUTE FUNCTION fn_enforce_service_order_timeline_actor_tenant();
""")
    )


def downgrade() -> None:
    op.execute(
        text("""
DROP TRIGGER IF EXISTS trg_service_order_timeline_actor_tenant ON service_order_timeline;
""")
    )
    op.execute(text("DROP FUNCTION IF EXISTS fn_enforce_service_order_timeline_actor_tenant();"))

    op.execute(
        text("""
DROP TRIGGER IF EXISTS trg_pdf_documents_order_tenant ON pdf_documents;
""")
    )
    op.execute(text("DROP FUNCTION IF EXISTS fn_enforce_pdf_document_order_tenant();"))

    op.execute(
        text("""
DROP TRIGGER IF EXISTS trg_inventory_movements_tenant_links ON inventory_movements;
""")
    )
    op.execute(text("DROP FUNCTION IF EXISTS fn_enforce_inventory_movement_tenant_links();"))
