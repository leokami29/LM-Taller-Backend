"""Utilidades compartidas entre scripts de semilla."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models.audit_log import AuditLog
from app.db.models.company import Company
from app.db.models.rbac import RoleChangeRequest, Site, TemporaryPermission, UserSiteRole
from app.db.models.customer import Customer
from app.db.models.equipment import Equipment
from app.db.models.inventory import InventoryItem, InventoryMovement
from app.db.models.order_number_sequence import OrderNumberSequence
from app.db.models.pdf_document import PDFDocument
from app.db.models.service_contract import ServiceContract
from app.db.models.service_order import ServiceOrder, ServiceOrderCostLine, ServiceOrderTimeline
from app.db.models.supplier import Supplier
from app.db.models.user import User


def delete_company_cascade(session: Session, company_id) -> None:
    """Elimina empresa y filas dependientes (orden estricto para FK)."""
    from app.db.models.customer_portal_user import CustomerPortalUser
    from app.db.models.equipment import EquipmentAttribute
    from app.db.models.inventory_category import InventoryCategory
    from app.db.models.service_order_image import ServiceOrderImage

    # 1. Permisos y auditoría (sin dependencias)
    session.execute(delete(TemporaryPermission).where(TemporaryPermission.company_id == company_id))
    session.execute(delete(RoleChangeRequest).where(RoleChangeRequest.company_id == company_id))
    session.execute(delete(AuditLog).where(AuditLog.company_id == company_id))

    # 2. IDs de órdenes e ítems para borrar hijos primero
    order_ids = list(
        session.scalars(select(ServiceOrder.id).where(ServiceOrder.company_id == company_id)).all()
    )
    item_ids = list(
        session.scalars(select(InventoryItem.id).where(InventoryItem.company_id == company_id)).all()
    )
    equip_ids = list(
        session.scalars(select(Equipment.id).where(Equipment.company_id == company_id)).all()
    )

    # 3. Hijos de órdenes
    if order_ids:
        session.execute(delete(PDFDocument).where(PDFDocument.service_order_id.in_(order_ids)))
        from app.db.models.service_order_image import ServiceOrderImage
        session.execute(delete(ServiceOrderImage).where(ServiceOrderImage.service_order_id.in_(order_ids)))
        session.execute(delete(ServiceOrderCostLine).where(ServiceOrderCostLine.service_order_id.in_(order_ids)))
        session.execute(delete(ServiceOrderTimeline).where(ServiceOrderTimeline.service_order_id.in_(order_ids)))
        session.execute(delete(InventoryMovement).where(InventoryMovement.service_order_id.in_(order_ids)))

    # 4. PDFs sin orden
    session.execute(delete(PDFDocument).where(
        PDFDocument.company_id == company_id,
        PDFDocument.service_order_id.is_(None),
    ))

    # 5. Las órdenes mismas (antes de contratos y clientes)
    session.execute(delete(ServiceOrder).where(ServiceOrder.company_id == company_id))

    # 6. Contratos (referencia clientes) — antes de borrar clientes
    session.execute(delete(ServiceContract).where(ServiceContract.company_id == company_id))

    # 7. Portal users (referencia clientes)
    session.execute(delete(CustomerPortalUser).where(CustomerPortalUser.company_id == company_id))

    # 8. Inventario
    if item_ids:
        session.execute(delete(InventoryMovement).where(InventoryMovement.inventory_item_id.in_(item_ids)))
    session.execute(delete(InventoryItem).where(InventoryItem.company_id == company_id))
    session.execute(delete(InventoryCategory).where(InventoryCategory.company_id == company_id))

    # 9. Equipos
    if equip_ids:
        session.execute(delete(EquipmentAttribute).where(EquipmentAttribute.equipment_id.in_(equip_ids)))
    session.execute(delete(Equipment).where(Equipment.company_id == company_id))

    # 10. Clientes
    session.execute(delete(Customer).where(Customer.company_id == company_id))

    # 11. Proveedores
    session.execute(delete(Supplier).where(Supplier.company_id == company_id))

    # 12. Secuencias, sedes, usuarios, empresa
    session.execute(delete(OrderNumberSequence).where(OrderNumberSequence.company_id == company_id))
    session.execute(delete(UserSiteRole).where(UserSiteRole.company_id == company_id))
    session.execute(delete(Site).where(Site.company_id == company_id))
    session.execute(delete(User).where(User.company_id == company_id))
    session.execute(delete(Company).where(Company.id == company_id))
    session.commit()
