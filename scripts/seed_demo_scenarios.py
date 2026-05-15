"""
Escenarios de semilla demo alineados con el esquema normalizado (líneas de costo, triggers, CHECK).

- Taller principal: casos extra (línea «otros», PDF sin orden, venta de stock, doble consumo en reparación).
- Taller secundario (902): dataset pequeño pero completo (usuarios, inventario, orden con líneas, timeline, PDFs).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dt import utc_now

from app.core.enums import (
    CostLineCategory,
    IdentificationType,
    InventoryMovementType,
    OrderPriority,
    OrderStatus,
    UserRole,
)
from app.db.models.company import Company
from app.db.models.customer import Customer
from app.db.models.equipment import Equipment
from app.db.models.inventory import InventoryItem, InventoryMovement
from app.db.models.pdf_document import PDFDocument
from app.db.models.service_order import ServiceOrder, ServiceOrderCostLine, ServiceOrderTimeline
from app.db.models.supplier import Supplier
from app.db.models.user import User
from app.services.order_service import recompute_total_cost
from scripts.seed_demo_constants import (
    DEMO_EMAIL_DOMAIN,
    DEMO_PASSWORD,
    SECOND_COMPANY_NAME,
    SECOND_DEMO_NIT,
)
from scripts.seed_demo_rbac import apply_demo_company_plan, ensure_demo_sites_secondary


def sync_cost_lines_from_order_aggregates(
    session: Session,
    company_id,
    orders: list[ServiceOrder],
    *,
    start_index: int = 1,
) -> None:
    """
    Para órdenes con costo > 0 a partir de start_index: una línea PARTS y una LABOR
    que replican los agregados legacy; luego recalcula totales (incluye categoría OTHER si existiera).
    La orden en índice 0 suele quedar solo con agregados 0 (sin líneas): caso «sin desglose».
    """
    for o in orders[start_index:]:
        if o.cost_parts and o.cost_parts > 0:
            session.add(
                ServiceOrderCostLine(
                    company_id=company_id,
                    service_order_id=o.id,
                    category=CostLineCategory.PARTS,
                    description="Repuestos (semilla demo)",
                    amount=o.cost_parts,
                    sort_order=0,
                )
            )
        if o.cost_labor and o.cost_labor > 0:
            session.add(
                ServiceOrderCostLine(
                    company_id=company_id,
                    service_order_id=o.id,
                    category=CostLineCategory.LABOR,
                    description="Mano de obra (semilla demo)",
                    amount=o.cost_labor,
                    sort_order=1,
                )
            )
    session.flush()
    for o in orders[start_index:]:
        recompute_total_cost(session, o)


def apply_primary_extended_scenarios(
    session: Session,
    *,
    company: Company,
    orders: list[ServiceOrder],
    admin: User,
    recep: User,
    tech1: User,
    tech2: User,
    inv_battery: InventoryItem,
    inv_case: InventoryItem,
) -> None:
    """Casos adicionales sobre el taller principal ya sembrado (órdenes + líneas base)."""

    # Línea OTHER: suma al total sin formar parte de repuestos ni MO (modelo normalizado).
    o_tab = orders[4]
    session.add(
        ServiceOrderCostLine(
            company_id=company.id,
            service_order_id=o_tab.id,
            category=CostLineCategory.OTHER,
            description="Logística / gestión de repuesto externo (demo)",
            amount=Decimal("15000"),
            sort_order=2,
        )
    )
    session.flush()
    recompute_total_cost(session, o_tab)

    # PDF ligado a orden + PDF solo a nivel empresa (listas, comunicación interna).
    session.add(
        PDFDocument(
            company_id=company.id,
            service_order_id=None,
            document_type="price_list",
            file_url="https://example.com/demo/pdf/lista-precios-interna-demo.pdf",
            generated_by_id=admin.id,
        )
    )

    # Venta de accesorio sin orden (retail / mostrador).
    session.add(
        InventoryMovement(
            inventory_item_id=inv_case.id,
            movement_type=InventoryMovementType.SALE,
            quantity_change=Decimal("-2"),
            service_order_id=None,
            notes="Venta mostrador — fundas universales (demo)",
            moved_by_id=recep.id,
        )
    )
    inv_case.quantity_stock = Decimal(inv_case.quantity_stock) - Decimal("2")

    # Segundo consumo en reparación: otro ítem, otra orden (CHECK used_in_repair + trigger tenant).
    session.add(
        InventoryMovement(
            inventory_item_id=inv_battery.id,
            movement_type=InventoryMovementType.USED_IN_REPAIR,
            quantity_change=Decimal("-1"),
            service_order_id=orders[2].id,
            notes="Batería retirada para diagnóstico en orden HP (demo)",
            moved_by_id=tech1.id,
        )
    )
    inv_battery.quantity_stock = Decimal(inv_battery.quantity_stock) - Decimal("1")

    # Timeline adicional coherente con estado final de la orden completada.
    session.add(
        ServiceOrderTimeline(
            service_order_id=orders[5].id,
            old_status=OrderStatus.IN_REPAIR.value,
            new_status=OrderStatus.COMPLETED.value,
            changed_by_id=tech2.id,
            notes="Pruebas finales digitalizador OK (semilla)",
            time_spent_seconds=3600,
        )
    )


def ensure_secondary_demodata(
    session: Session,
    pwd_hash: str,
    *,
    fixed_company_id: UUID | None = None,
) -> None:
    """
    Segundo tenant con el mismo patrón normalizado: proveedor, ítems, movimientos,
    orden ORD-000001 con líneas de costo, timeline, consumo used_in_repair con orden, PDFs.
    Idempotente: si el NIT 902 ya existe, no duplica.
    """
    if fixed_company_id is not None:
        if session.scalar(select(Company).where(Company.id == fixed_company_id)):
            print(f"  Tenant secundario ya existe (company_id {fixed_company_id}).")
            return
    elif session.scalar(select(Company).where(Company.nit_rut == SECOND_DEMO_NIT)):
        print(f"  Tenant secundario ya existe (NIT {SECOND_DEMO_NIT}).")
        return

    company_kw = dict(
        name=SECOND_COMPANY_NAME,
        nit_rut=SECOND_DEMO_NIT,
        address="Av. Boyacá # 170, Bogotá",
        phone="+57 601 5550200",
        email=f"contacto.norte@{DEMO_EMAIL_DOMAIN}",
        country="Colombia",
        currency="COP",
        is_active=True,
        settings_json={"theme": "light", "locale": "es-CO", "seed": "demo-secondary-v2"},
        next_order_number=1,
    )
    if fixed_company_id is not None:
        company_kw["id"] = fixed_company_id
    company = Company(**company_kw)
    session.add(company)
    session.flush()
    apply_demo_company_plan(session, company)

    admin = User(
        company_id=company.id,
        email=f"admin.norte@{DEMO_EMAIL_DOMAIN}",
        full_name="Diego Admin Norte",
        hashed_password=pwd_hash,
        role=UserRole.ADMIN,
        phone="3002220001",
    )
    recep = User(
        company_id=company.id,
        email=f"recepcion.norte@{DEMO_EMAIL_DOMAIN}",
        full_name="Valentina Recepción Norte",
        hashed_password=pwd_hash,
        role=UserRole.RECEPTION,
        phone="3002220002",
    )
    tech = User(
        company_id=company.id,
        email=f"tecnico.norte@{DEMO_EMAIL_DOMAIN}",
        full_name="Mateo Técnico Norte",
        hashed_password=pwd_hash,
        role=UserRole.TECHNICIAN,
        phone="3002220003",
    )
    session.add_all([admin, recep, tech])
    session.flush()
    admin.created_by_id = admin.id
    recep.created_by_id = admin.id
    tech.created_by_id = admin.id

    ensure_demo_sites_secondary(session, company, admin=admin, recep=recep, tech=tech)

    sup = Supplier(
        company_id=company.id,
        name="Distribuidora Norte SAS",
        contact_person="Compras Norte",
        email=f"compras@dist-norte.{DEMO_EMAIL_DOMAIN}",
        phone="6012223344",
        address="Cota",
        payment_terms="15 días",
    )
    session.add(sup)
    session.flush()

    inv_lcd = InventoryItem(
        company_id=company.id,
        item_type="repuesto",
        sku="NORTE-LCD-GEN",
        name="Pantalla genérica 6.5",
        category="Pantallas",
        quantity_stock=Decimal("6"),
        quantity_minimum=Decimal("2"),
        unit_cost=Decimal("120000"),
        unit_price=Decimal("210000"),
        supplier_id=sup.id,
        photos_urls=[],
        barcode="7700001122334",
        weight=Decimal("0.070"),
        dimensions_json={},
    )
    inv_glue = InventoryItem(
        company_id=company.id,
        item_type="consumible",
        sku="NORTE-PEG-B7000",
        name="Pegamento B-7000 15ml",
        category="Laboratorio",
        quantity_stock=Decimal("20"),
        quantity_minimum=Decimal("5"),
        unit_cost=Decimal("8000"),
        unit_price=Decimal("15000"),
        supplier_id=sup.id,
        photos_urls=[],
        barcode=None,
        weight=Decimal("0.020"),
        dimensions_json={},
    )
    session.add_all([inv_lcd, inv_glue])
    session.flush()

    session.add(
        InventoryMovement(
            inventory_item_id=inv_lcd.id,
            movement_type=InventoryMovementType.PURCHASE,
            quantity_change=Decimal("6"),
            service_order_id=None,
            notes="Stock inicial demo tenant norte",
            moved_by_id=admin.id,
        )
    )

    cust = Customer(
        company_id=company.id,
        first_name="Cliente",
        last_name="Norte",
        email=f"cliente.norte@{DEMO_EMAIL_DOMAIN}",
        phone="3102220001",
        address="Chía",
        identification_type=IdentificationType.CC,
        identification_number="80112233",
        city="Cundinamarca",
        country="Colombia",
        metadata_json={"tenant": "secondary-demo"},
    )
    session.add(cust)
    session.flush()

    eq = Equipment(
        company_id=company.id,
        serial_number="NORTE-EQ-001",
        equipment_type="smartphone",
        brand="Motorola",
        model="Edge 40",
        imei="356600112233445",
        color="Azul",
        original_owner_id=cust.id,
        photos_urls=[],
        additional_notes="Equipo demo tenant secundario",
        first_received_date=utc_now().date() - timedelta(days=3),
    )
    session.add(eq)
    session.flush()

    order = ServiceOrder(
        company_id=company.id,
        order_number="ORD-000001",
        equipment_id=eq.id,
        current_customer_id=cust.id,
        status=OrderStatus.IN_REPAIR,
        priority=OrderPriority.MEDIUM,
        assigned_to_id=tech.id,
        problem_description="Pantalla con líneas verticales tras caída (demo multi-tenant).",
        diagnosis_notes="Matriz OK; revisar flex y conector.",
        estimated_completion=utc_now() + timedelta(days=2),
        cost_parts=Decimal("95000"),
        cost_labor=Decimal("60000"),
        total_cost=Decimal("155000"),
        created_by_id=recep.id,
    )
    session.add(order)
    session.flush()

    session.add_all(
        [
            ServiceOrderCostLine(
                company_id=company.id,
                service_order_id=order.id,
                category=CostLineCategory.PARTS,
                description="Pantalla genérica + kit pegamento (demo norte)",
                amount=Decimal("95000"),
                sort_order=0,
            ),
            ServiceOrderCostLine(
                company_id=company.id,
                service_order_id=order.id,
                category=CostLineCategory.LABOR,
                description="Desmontaje y prueba (demo norte)",
                amount=Decimal("60000"),
                sort_order=1,
            ),
        ]
    )
    session.flush()
    recompute_total_cost(session, order)

    session.add_all(
        [
            ServiceOrderTimeline(
                service_order_id=order.id,
                old_status=None,
                new_status=OrderStatus.RECEIVED.value,
                changed_by_id=recep.id,
                notes="Ingreso recepción norte",
                time_spent_seconds=None,
            ),
            ServiceOrderTimeline(
                service_order_id=order.id,
                old_status=OrderStatus.RECEIVED.value,
                new_status=OrderStatus.IN_REPAIR.value,
                changed_by_id=tech.id,
                notes="En banco de reparación",
                time_spent_seconds=900,
            ),
        ]
    )

    session.add(
        InventoryMovement(
            inventory_item_id=inv_glue.id,
            movement_type=InventoryMovementType.USED_IN_REPAIR,
            quantity_change=Decimal("-1"),
            service_order_id=order.id,
            notes="Consumo pegamento en reparación Motorola (demo norte)",
            moved_by_id=tech.id,
        )
    )
    inv_glue.quantity_stock = Decimal(inv_glue.quantity_stock) - Decimal("1")

    session.add_all(
        [
            PDFDocument(
                company_id=company.id,
                service_order_id=order.id,
                document_type="work_order",
                file_url="https://example.com/demo/norte/orden-000001.pdf",
                generated_by_id=recep.id,
            ),
            PDFDocument(
                company_id=company.id,
                service_order_id=None,
                document_type="internal_memo",
                file_url="https://example.com/demo/norte/memo-politicas-bodega.pdf",
                generated_by_id=admin.id,
            ),
        ]
    )

    company.next_order_number = max(int(company.next_order_number or 1), 10)

    print(f"  Creado tenant secundario: {company.name} (NIT {SECOND_DEMO_NIT})")
    print(f"    Admin: admin.norte@{DEMO_EMAIL_DOMAIN} / {DEMO_PASSWORD}")
    print(f"    Recepción: recepcion.norte@{DEMO_EMAIL_DOMAIN} / {DEMO_PASSWORD}")
    print(f"    Técnico: tecnico.norte@{DEMO_EMAIL_DOMAIN} / {DEMO_PASSWORD}")
