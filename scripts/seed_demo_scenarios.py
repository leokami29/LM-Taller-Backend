"""
Escenarios de semilla demo alineados con el esquema normalizado.

- Taller principal: escenarios extra sobre las primeras 8 órdenes activas
  (línea «otros», PDF sin orden, venta de stock, doble consumo).
- Taller secundario (902): dataset más completo — 4 órdenes con todos los
  estados, 2 técnicos, 2 sedes, timelines, líneas de costo, PDFs y movimientos.
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
    ContractKind,
    IdentificationType,
    InventoryMovementType,
    OrderPriority,
    OrderStatus,
    ServiceOrderKind,
    UserRole,
)
from app.db.models.company import Company
from app.db.models.customer import Customer
from app.db.models.equipment import Equipment
from app.db.models.inventory import InventoryItem, InventoryMovement
from app.db.models.inventory_category import InventoryCategory
from app.db.models.pdf_document import PDFDocument
from app.db.models.service_contract import ServiceContract
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


# ---------------------------------------------------------------------------
# Helpers compartidos
# ---------------------------------------------------------------------------

def sync_cost_lines_from_order_aggregates(
    session: Session,
    company_id,
    orders: list[ServiceOrder],
    *,
    start_index: int = 1,
) -> None:
    """
    Para órdenes con costo > 0 a partir de start_index: una línea PARTS y una LABOR.
    Luego recalcula totales.
    """
    for o in orders[start_index:]:
        if o.cost_parts and o.cost_parts > 0:
            session.add(ServiceOrderCostLine(
                company_id=company_id,
                service_order_id=o.id,
                category=CostLineCategory.PARTS,
                description="Repuestos (semilla demo)",
                amount=o.cost_parts,
                sort_order=0,
            ))
        if o.cost_labor and o.cost_labor > 0:
            session.add(ServiceOrderCostLine(
                company_id=company_id,
                service_order_id=o.id,
                category=CostLineCategory.LABOR,
                description="Mano de obra (semilla demo)",
                amount=o.cost_labor,
                sort_order=1,
            ))
    session.flush()
    for o in orders[start_index:]:
        recompute_total_cost(session, o)


# ---------------------------------------------------------------------------
# Escenarios adicionales sobre el taller principal ya sembrado
# ---------------------------------------------------------------------------

def apply_primary_extended_scenarios(
    session: Session,
    *,
    company: Company,
    orders: list[ServiceOrder],
    admin: User,
    recep: User,
    tech1: User,
    tech2: User,
    tech3: User | None = None,
    tech4: User | None = None,
    tech5: User | None = None,
    inv_battery: InventoryItem,
    inv_case: InventoryItem,
) -> None:
    """Casos adicionales sobre el taller principal ya sembrado."""

    # Línea OTHER en la primera orden con costos
    first_with_cost = next(
        (o for o in orders if o.cost_parts and o.cost_parts > 0), None
    )
    if first_with_cost:
        session.add(ServiceOrderCostLine(
            company_id=company.id,
            service_order_id=first_with_cost.id,
            category=CostLineCategory.OTHER,
            description="Logística / gestión de repuesto externo (demo)",
            amount=Decimal("15000"),
            sort_order=2,
        ))
        session.flush()
        recompute_total_cost(session, first_with_cost)

    # PDF ligado a empresa (lista de precios interna) — sin orden
    session.add(PDFDocument(
        company_id=company.id,
        service_order_id=None,
        document_type="price_list",
        file_url="https://example.com/demo/pdf/lista-precios-interna-demo.pdf",
        generated_by_id=admin.id,
    ))

    # Venta de accesorio sin orden (retail / mostrador)
    session.add(InventoryMovement(
        inventory_item_id=inv_case.id,
        movement_type=InventoryMovementType.SALE,
        quantity_change=Decimal("-2"),
        service_order_id=None,
        notes="Venta mostrador — fundas universales (demo)",
        moved_by_id=recep.id,
    ))
    inv_case.quantity_stock = Decimal(str(inv_case.quantity_stock)) - Decimal("2")

    # Segundo consumo en reparación: batería en otra orden
    if len(orders) >= 3:
        target_order = orders[2]
        session.add(InventoryMovement(
            inventory_item_id=inv_battery.id,
            movement_type=InventoryMovementType.USED_IN_REPAIR,
            quantity_change=Decimal("-1"),
            service_order_id=target_order.id,
            notes="Batería retirada para diagnóstico (demo)",
            moved_by_id=tech1.id,
        ))
        inv_battery.quantity_stock = Decimal(str(inv_battery.quantity_stock)) - Decimal("1")

    # Timeline adicional coherente con una orden completada (si existe)
    completed_order = next(
        (o for o in orders if o.status == OrderStatus.COMPLETED), None
    )
    if completed_order:
        session.add(ServiceOrderTimeline(
            service_order_id=completed_order.id,
            old_status=OrderStatus.IN_REPAIR.value,
            new_status=OrderStatus.COMPLETED.value,
            changed_by_id=tech2.id,
            notes="Pruebas finales OK (semilla extendida)",
            time_spent_seconds=3600,
        ))


# ---------------------------------------------------------------------------
# Tenant secundario — dataset amplio (4 órdenes, 2 técnicos, 2 sedes)
# ---------------------------------------------------------------------------

def ensure_secondary_demodata(
    session: Session,
    pwd_hash: str,
    *,
    fixed_company_id: UUID | None = None,
) -> None:
    """
    Segundo tenant con dataset completo:
    - 2 técnicos, 2 sedes (Principal + Punto Boyacá)
    - 4 órdenes cubriendo todos los estados activos: received, in_repair, completed, cancelled
    - Inventario: 3 ítems, 2 categorías
    - Movimientos de stock (purchase + used_in_repair)
    - Líneas de costo en órdenes con costos
    - Timelines completas
    - 1 contrato de servicio
    - PDFs: work_order + memo interno
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
        settings_json={"theme": "light", "locale": "es-CO", "seed": "demo-secondary-v3"},
        next_order_number=1,
    )
    if fixed_company_id is not None:
        company_kw["id"] = fixed_company_id
    company = Company(**company_kw)
    session.add(company)
    session.flush()
    apply_demo_company_plan(session, company)

    # --- Usuarios ---
    admin = User(company_id=company.id, email=f"admin.norte@{DEMO_EMAIL_DOMAIN}",
                 full_name="Diego Admin Norte", hashed_password=pwd_hash,
                 role=UserRole.ADMIN, phone="3002220001")
    recep = User(company_id=company.id, email=f"recepcion.norte@{DEMO_EMAIL_DOMAIN}",
                 full_name="Valentina Recepción Norte", hashed_password=pwd_hash,
                 role=UserRole.RECEPTION, phone="3002220002")
    tech_a = User(company_id=company.id, email=f"tecnico.norte@{DEMO_EMAIL_DOMAIN}",
                  full_name="Mateo Técnico Norte", hashed_password=pwd_hash,
                  role=UserRole.TECHNICIAN, phone="3002220003")
    tech_b = User(company_id=company.id, email=f"tecnico2.norte@{DEMO_EMAIL_DOMAIN}",
                  full_name="Paola Técnico Norte", hashed_password=pwd_hash,
                  role=UserRole.TECHNICIAN, phone="3002220004")
    session.add_all([admin, recep, tech_a, tech_b])
    session.flush()
    admin.created_by_id = admin.id
    recep.created_by_id = admin.id
    tech_a.created_by_id = admin.id
    tech_b.created_by_id = admin.id

    principal_site = ensure_demo_sites_secondary(
        session, company, admin=admin, recep=recep, tech=tech_a
    )

    # --- Proveedor ---
    sup = Supplier(company_id=company.id, name="Distribuidora Norte SAS",
                   contact_person="Compras Norte",
                   email=f"compras@dist-norte.{DEMO_EMAIL_DOMAIN}",
                   phone="6012223344", address="Cota", payment_terms="15 días")
    session.add(sup)
    session.flush()

    # --- Categorías de inventario ---
    cat_pant = InventoryCategory(company_id=company.id, name="Pantallas", color="#3b82f6")
    cat_lab = InventoryCategory(company_id=company.id, name="Laboratorio", color="#10b981")
    cat_bat = InventoryCategory(company_id=company.id, name="Baterías", color="#f59e0b")
    session.add_all([cat_pant, cat_lab, cat_bat])
    session.flush()

    # --- Inventario ---
    inv_lcd = InventoryItem(
        company_id=company.id, item_type="repuesto", sku="NORTE-LCD-GEN",
        name="Pantalla genérica 6.5\"", category="Pantallas",
        quantity_stock=Decimal("6"), quantity_minimum=Decimal("2"),
        unit_cost=Decimal("120000"), unit_price=Decimal("210000"),
        supplier_id=sup.id, barcode="7700001122334", weight=Decimal("0.070"),
        dimensions_json={})
    inv_glue = InventoryItem(
        company_id=company.id, item_type="consumible", sku="NORTE-PEG-B7000",
        name="Pegamento B-7000 15ml", category="Laboratorio",
        quantity_stock=Decimal("18"), quantity_minimum=Decimal("5"),
        unit_cost=Decimal("8000"), unit_price=Decimal("15000"),
        supplier_id=sup.id, weight=Decimal("0.020"), dimensions_json={})
    inv_bat_norte = InventoryItem(
        company_id=company.id, item_type="repuesto", sku="NORTE-BAT-MOT",
        name="Batería Motorola Edge 40", category="Baterías",
        quantity_stock=Decimal("1"), quantity_minimum=Decimal("3"),
        unit_cost=Decimal("75000"), unit_price=Decimal("140000"),
        supplier_id=sup.id, weight=Decimal("0.048"), dimensions_json={})
    session.add_all([inv_lcd, inv_glue, inv_bat_norte])
    session.flush()

    session.add_all([
        InventoryMovement(inventory_item_id=inv_lcd.id,
                          movement_type=InventoryMovementType.PURCHASE,
                          quantity_change=Decimal("6"),
                          notes="Stock inicial demo tenant norte", moved_by_id=admin.id),
        InventoryMovement(inventory_item_id=inv_glue.id,
                          movement_type=InventoryMovementType.PURCHASE,
                          quantity_change=Decimal("20"),
                          notes="Compra inicial pegamento", moved_by_id=admin.id),
        InventoryMovement(inventory_item_id=inv_bat_norte.id,
                          movement_type=InventoryMovementType.PURCHASE,
                          quantity_change=Decimal("3"),
                          notes="Stock inicial baterías Motorola", moved_by_id=admin.id),
    ])

    # --- Clientes ---
    cust1 = Customer(company_id=company.id, first_name="Cliente", last_name="Norte",
                     email=f"cliente.norte@{DEMO_EMAIL_DOMAIN}", phone="3102220001",
                     address="Chía", identification_type=IdentificationType.CC,
                     identification_number="80112233", city="Cundinamarca", country="Colombia",
                     metadata_json={"tenant": "secondary-demo"})
    cust2 = Customer(company_id=company.id, first_name="Empresa", last_name="Boyacá SAS",
                     email=f"empresa.boyaca@{DEMO_EMAIL_DOMAIN}", phone="6012229988",
                     identification_type=IdentificationType.NIT, identification_number="901556677-1",
                     city="Tunja", country="Colombia", metadata_json={})
    session.add_all([cust1, cust2])
    session.flush()

    # --- Equipos ---
    eq_a = Equipment(company_id=company.id, serial_number="NORTE-EQ-001",
                     equipment_type="smartphone", brand="Motorola", model="Edge 40",
                     imei="356600112233445", color="Azul", original_owner_id=cust1.id,
                     photos_urls=[], additional_notes="Equipo demo tenant secundario",
                     first_received_date=utc_now().date() - timedelta(days=3))
    eq_b = Equipment(company_id=company.id, serial_number="NORTE-EQ-002",
                     equipment_type="laptop", brand="Asus", model="VivoBook 15",
                     color="Plata", original_owner_id=cust2.id, photos_urls=[],
                     additional_notes="Laptop corporativa — derrame de líquido")
    eq_c = Equipment(company_id=company.id, serial_number="NORTE-EQ-003",
                     equipment_type="smartphone", brand="Samsung", model="Galaxy A34",
                     imei="351122334455667", color="Negro", original_owner_id=cust1.id,
                     photos_urls=[], additional_notes="Pantalla rota al lado")
    session.add_all([eq_a, eq_b, eq_c])
    session.flush()

    # --- Contrato de servicio ---
    contract = ServiceContract(
        company_id=company.id, customer_id=cust2.id,
        contract_number="NORTE-CONTRACT-001",
        name="Mantenimiento Empresa Boyacá",
        contract_kind=ContractKind.MAINTENANCE,
        default_site_id=principal_site.id,
        allowed_order_kinds=[ServiceOrderKind.WORKSHOP_INTAKE_CONTRACT.value],
        template_json={"version": 1, "fields": []},
        valid_from=utc_now().date() - timedelta(days=30),
        valid_to=utc_now().date() + timedelta(days=335),
        is_active=True,
    )
    session.add(contract)
    session.flush()

    now = utc_now()

    def _mk(num, eq, cust, status, priority, tech, problem, diag, cp, cl, da=0, kind=ServiceOrderKind.WORKSHOP_INTAKE):
        so = ServiceOrder(
            company_id=company.id, order_number=f"ORD-{num:06d}",
            equipment_id=eq.id, current_customer_id=cust.id,
            status=status, priority=priority,
            assigned_to_id=tech.id if tech else None,
            problem_description=problem, diagnosis_notes=diag,
            cost_parts=cp, cost_labor=cl, total_cost=cp + cl,
            created_by_id=recep.id, order_kind=kind,
            site_id=principal_site.id,
            actual_completion=now - timedelta(days=max(0, da - 1)) if status in (OrderStatus.COMPLETED, OrderStatus.DELIVERED) else None,
            estimated_completion=now + timedelta(days=2) if status not in (OrderStatus.DELIVERED, OrderStatus.CANCELLED, OrderStatus.COMPLETED) else None,
        )
        if da:
            so.created_at = now - timedelta(days=da)
            so.updated_at = so.created_at
        return so

    # 4 órdenes cubriendo: in_repair, received, completed, cancelled
    order1 = _mk(1, eq_a, cust1, OrderStatus.IN_REPAIR, OrderPriority.MEDIUM,
                 tech_a, "Pantalla con líneas verticales tras caída.",
                 "Matriz OK; revisar flex y conector.",
                 Decimal("95000"), Decimal("60000"), da=4)
    order2 = _mk(2, eq_b, cust2, OrderStatus.RECEIVED, OrderPriority.HIGH,
                 tech_b, "Laptop no enciende — derrame de café.",
                 None, Decimal("0"), Decimal("0"), da=1)
    order3 = _mk(3, eq_c, cust1, OrderStatus.COMPLETED, OrderPriority.LOW,
                 tech_a, "Pantalla quebrada en borde.",
                 "Pantalla genérica instalada y calibrada.",
                 Decimal("120000"), Decimal("60000"), da=15)
    order3.actual_completion = now - timedelta(days=14)
    order4 = _mk(4, eq_a, cust2, OrderStatus.CANCELLED, OrderPriority.LOW,
                 None, "Actualización de software solicitada — cancelada.",
                 "Sin intervención realizada.",
                 Decimal("0"), Decimal("0"), da=30)

    session.add_all([order1, order2, order3, order4])
    session.flush()

    # Líneas de costo
    for order in [order1, order3]:
        if order.cost_parts > 0:
            session.add(ServiceOrderCostLine(
                company_id=company.id, service_order_id=order.id,
                category=CostLineCategory.PARTS,
                description="Pantalla y materiales (demo norte)",
                amount=order.cost_parts, sort_order=0))
        if order.cost_labor > 0:
            session.add(ServiceOrderCostLine(
                company_id=company.id, service_order_id=order.id,
                category=CostLineCategory.LABOR,
                description="Mano de obra (demo norte)",
                amount=order.cost_labor, sort_order=1))
    session.flush()
    for order in [order1, order3]:
        recompute_total_cost(session, order)

    # Timelines
    session.add_all([
        # order1 — IN_REPAIR
        ServiceOrderTimeline(service_order_id=order1.id, old_status=None,
                             new_status=OrderStatus.RECEIVED.value,
                             changed_by_id=recep.id, notes="Ingreso recepción norte"),
        ServiceOrderTimeline(service_order_id=order1.id,
                             old_status=OrderStatus.RECEIVED.value,
                             new_status=OrderStatus.IN_REPAIR.value,
                             changed_by_id=tech_a.id, notes="En banco de reparación",
                             time_spent_seconds=900),
        # order2 — RECEIVED
        ServiceOrderTimeline(service_order_id=order2.id, old_status=None,
                             new_status=OrderStatus.RECEIVED.value,
                             changed_by_id=recep.id, notes="Laptop con daño por líquido"),
        # order3 — COMPLETED (flujo completo)
        ServiceOrderTimeline(service_order_id=order3.id, old_status=None,
                             new_status=OrderStatus.RECEIVED.value,
                             changed_by_id=recep.id, notes="Samsung A34 pantalla rota"),
        ServiceOrderTimeline(service_order_id=order3.id,
                             old_status=OrderStatus.RECEIVED.value,
                             new_status=OrderStatus.DIAGNOSING.value,
                             changed_by_id=tech_a.id, notes="Diagnóstico: pantalla rota borde",
                             time_spent_seconds=1200),
        ServiceOrderTimeline(service_order_id=order3.id,
                             old_status=OrderStatus.DIAGNOSING.value,
                             new_status=OrderStatus.IN_REPAIR.value,
                             changed_by_id=tech_a.id, notes="Instalando pantalla genérica",
                             time_spent_seconds=3600),
        ServiceOrderTimeline(service_order_id=order3.id,
                             old_status=OrderStatus.IN_REPAIR.value,
                             new_status=OrderStatus.COMPLETED.value,
                             changed_by_id=tech_a.id, notes="Calibración táctil OK",
                             time_spent_seconds=900),
        # order4 — CANCELLED
        ServiceOrderTimeline(service_order_id=order4.id, old_status=None,
                             new_status=OrderStatus.RECEIVED.value,
                             changed_by_id=recep.id, notes="Solicitud actualización SW"),
        ServiceOrderTimeline(service_order_id=order4.id,
                             old_status=OrderStatus.RECEIVED.value,
                             new_status=OrderStatus.CANCELLED.value,
                             changed_by_id=admin.id, notes="Cliente canceló — sin intervención"),
    ])

    # Movimientos ligados a órdenes
    session.add_all([
        InventoryMovement(inventory_item_id=inv_glue.id,
                          movement_type=InventoryMovementType.USED_IN_REPAIR,
                          quantity_change=Decimal("-1"),
                          service_order_id=order1.id,
                          notes="Pegamento en reparación Motorola", moved_by_id=tech_a.id),
        InventoryMovement(inventory_item_id=inv_lcd.id,
                          movement_type=InventoryMovementType.USED_IN_REPAIR,
                          quantity_change=Decimal("-1"),
                          service_order_id=order3.id,
                          notes="Pantalla genérica instalada en A34", moved_by_id=tech_a.id),
        InventoryMovement(inventory_item_id=inv_bat_norte.id,
                          movement_type=InventoryMovementType.ADJUSTMENT,
                          quantity_change=Decimal("-2"),
                          service_order_id=None,
                          notes="Ajuste conteo físico — unidades defectuosas", moved_by_id=admin.id),
    ])
    inv_glue.quantity_stock = Decimal("18") - Decimal("1")
    inv_lcd.quantity_stock = Decimal("6") - Decimal("1")
    inv_bat_norte.quantity_stock = Decimal("1") - Decimal("0") + Decimal("3") - Decimal("2")  # = 2 neto

    # PDFs
    session.add_all([
        PDFDocument(company_id=company.id, service_order_id=order1.id,
                    document_type="work_order",
                    file_url="https://example.com/demo/norte/orden-000001.pdf",
                    generated_by_id=recep.id),
        PDFDocument(company_id=company.id, service_order_id=order3.id,
                    document_type="delivery_receipt",
                    file_url="https://example.com/demo/norte/entrega-000003.pdf",
                    generated_by_id=recep.id),
        PDFDocument(company_id=company.id, service_order_id=None,
                    document_type="internal_memo",
                    file_url="https://example.com/demo/norte/memo-politicas-bodega.pdf",
                    generated_by_id=admin.id),
    ])

    company.next_order_number = max(int(company.next_order_number or 1), 10)

    print(f"  Creado tenant secundario: {company.name} (NIT {SECOND_DEMO_NIT})")
    print(f"    Admin: admin.norte@{DEMO_EMAIL_DOMAIN} / {DEMO_PASSWORD}")
    print(f"    Recepción: recepcion.norte@{DEMO_EMAIL_DOMAIN} / {DEMO_PASSWORD}")
    print(f"    Técnico A: tecnico.norte@{DEMO_EMAIL_DOMAIN} / {DEMO_PASSWORD}")
    print(f"    Técnico B: tecnico2.norte@{DEMO_EMAIL_DOMAIN} / {DEMO_PASSWORD}")
