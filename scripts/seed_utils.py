"""Utilidades compartidas entre scripts de semilla."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models.audit_log import AuditLog
from app.db.models.company import Company
from app.db.models.customer import Customer
from app.db.models.equipment import Equipment
from app.db.models.inventory import InventoryItem, InventoryMovement
from app.db.models.pdf_document import PDFDocument
from app.db.models.service_order import ServiceOrder, ServiceOrderTimeline
from app.db.models.supplier import Supplier
from app.db.models.user import User


def delete_company_cascade(session: Session, company_id) -> None:
    """Elimina empresa y filas dependientes (orden seguro para FK)."""
    session.execute(delete(AuditLog).where(AuditLog.company_id == company_id))
    session.execute(delete(PDFDocument).where(PDFDocument.company_id == company_id))

    item_ids = list(
        session.scalars(select(InventoryItem.id).where(InventoryItem.company_id == company_id)).all()
    )
    if item_ids:
        session.execute(delete(InventoryMovement).where(InventoryMovement.inventory_item_id.in_(item_ids)))

    order_ids = list(
        session.scalars(select(ServiceOrder.id).where(ServiceOrder.company_id == company_id)).all()
    )
    if order_ids:
        session.execute(delete(ServiceOrderTimeline).where(ServiceOrderTimeline.service_order_id.in_(order_ids)))
        session.execute(delete(InventoryMovement).where(InventoryMovement.service_order_id.in_(order_ids)))
        session.execute(delete(ServiceOrder).where(ServiceOrder.company_id == company_id))

    session.execute(delete(InventoryItem).where(InventoryItem.company_id == company_id))
    session.execute(delete(Equipment).where(Equipment.company_id == company_id))
    session.execute(delete(Customer).where(Customer.company_id == company_id))
    session.execute(delete(Supplier).where(Supplier.company_id == company_id))
    session.execute(delete(User).where(User.company_id == company_id))
    session.execute(delete(Company).where(Company.id == company_id))
    session.commit()
