from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core.dt import utc_now
from app.core.enums import InventoryMovementType
from app.core.exceptions import InsufficientStockError
from app.db.models.inventory import InventoryItem, InventoryMovement


def apply_stock_change(
    db: Session,
    *,
    item: InventoryItem,
    company_id,
    movement_type: InventoryMovementType,
    quantity_change: Decimal,
    moved_by_id,
    service_order_id: Optional[object] = None,
    notes: Optional[str] = None,
) -> InventoryMovement:
    if item.company_id != company_id:
        raise ValueError("Ítem no pertenece a la empresa")

    if movement_type == InventoryMovementType.USED_IN_REPAIR and service_order_id is None:
        raise ValueError("El consumo en reparación (used_in_repair) debe ir asociado a una orden de servicio")

    current = Decimal(item.quantity_stock or 0)
    delta = Decimal(quantity_change)
    new_qty = current + delta
    if new_qty < 0:
        raise InsufficientStockError("El stock resultante no puede ser negativo")

    item.quantity_stock = new_qty
    if movement_type == InventoryMovementType.PURCHASE and delta > 0:
        item.last_restocked_at = utc_now()

    db.add(item)
    movement = InventoryMovement(
        inventory_item_id=item.id,
        movement_type=movement_type,
        quantity_change=delta,
        service_order_id=service_order_id,
        notes=notes,
        moved_by_id=moved_by_id,
    )
    db.add(movement)
    return movement
