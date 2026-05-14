"""Dataset demo del taller principal (una empresa por sesión / BD)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.dt import utc_now
from app.core.enums import (
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
from app.db.models.service_order import ServiceOrder, ServiceOrderTimeline
from app.db.models.supplier import Supplier
from app.db.models.user import User
from scripts.seed_demo_constants import DEMO_EMAIL_DOMAIN, DEMO_NIT
from scripts.seed_demo_scenarios import apply_primary_extended_scenarios, sync_cost_lines_from_order_aggregates


def populate_primary_demo_company(
    session: Session,
    *,
    pwd_hash: str,
    fixed_company_id: UUID | None = None,
) -> Company:

    company_kw = dict(
        name="Taller Central Demo SG",
        nit_rut=DEMO_NIT,
        address="Carrera 15 # 90-10, Bogotá",
        phone="+57 601 5550100",
        email=f"contacto@{DEMO_EMAIL_DOMAIN}",
        country="Colombia",
        currency="COP",
        is_active=True,
        settings_json={"theme": "light", "locale": "es-CO", "seed": "demo"},
        next_order_number=1,
    )
    if fixed_company_id is not None:
        company_kw["id"] = fixed_company_id
    company = Company(**company_kw)
    session.add(company)
    session.flush()

    admin = User(
        company_id=company.id,
        email=f"admin@{DEMO_EMAIL_DOMAIN}",
        full_name="Laura Admin",
        hashed_password=pwd_hash,
        role=UserRole.ADMIN,
        phone="3001110001",
    )
    recep = User(
        company_id=company.id,
        email=f"recepcion@{DEMO_EMAIL_DOMAIN}",
        full_name="Carlos Recepción",
        hashed_password=pwd_hash,
        role=UserRole.RECEPTION,
        phone="3001110002",
    )
    tech1 = User(
        company_id=company.id,
        email=f"tecnico1@{DEMO_EMAIL_DOMAIN}",
        full_name="María Técnico",
        hashed_password=pwd_hash,
        role=UserRole.TECHNICIAN,
        phone="3001110003",
    )
    tech2 = User(
        company_id=company.id,
        email=f"tecnico2@{DEMO_EMAIL_DOMAIN}",
        full_name="Jorge Técnico",
        hashed_password=pwd_hash,
        role=UserRole.TECHNICIAN,
        phone="3001110004",
    )
    viewer = User(
        company_id=company.id,
        email=f"visitante@{DEMO_EMAIL_DOMAIN}",
        full_name="Ana Solo lectura",
        hashed_password=pwd_hash,
        role=UserRole.VIEWER,
    )
    inactive = User(
        company_id=company.id,
        email=f"baja@{DEMO_EMAIL_DOMAIN}",
        full_name="Usuario inactivo",
        hashed_password=pwd_hash,
        role=UserRole.VIEWER,
        is_active=False,
    )
    session.add_all([admin, recep, tech1, tech2, viewer, inactive])
    session.flush()
    admin.created_by_id = admin.id
    recep.created_by_id = admin.id
    tech1.created_by_id = admin.id
    tech2.created_by_id = admin.id
    viewer.created_by_id = admin.id
    inactive.created_by_id = admin.id

    # Clientes: varios perfiles (email único por empresa en modelo)
    c1 = Customer(
        company_id=company.id,
        first_name="Pedro",
        last_name="Gómez",
        email=f"pedro.gomez@{DEMO_EMAIL_DOMAIN}",
        phone="3101234501",
        address="Calle 100 # 45",
        identification_type=IdentificationType.CC,
        identification_number="1023456789",
        city="Bogotá",
        country="Colombia",
        metadata_json={"vip": True, "notes": "Prefiere contacto por WhatsApp"},
    )
    c2 = Customer(
        company_id=company.id,
        first_name="Lucía",
        last_name="Martínez",
        email=f"lucia.martinez@{DEMO_EMAIL_DOMAIN}",
        phone="3209876502",
        address="Av. El Dorado",
        identification_type=IdentificationType.NIT,
        identification_number="900555221-1",
        city="Bogotá",
        country="Colombia",
        metadata_json={},
    )
    c3 = Customer(
        company_id=company.id,
        first_name="Empresa",
        last_name="Sin email S.A.S.",
        email=None,
        phone="6014445566",
        address="Zona industrial",
        identification_type=IdentificationType.NIT,
        identification_number="860001025",
        city="Medellín",
        country="Colombia",
        metadata_json={"billing": "30 días"},
    )
    c4 = Customer(
        company_id=company.id,
        first_name="John",
        last_name="Smith",
        email=f"john.smith@{DEMO_EMAIL_DOMAIN}",
        phone="+1 305 0001111",
        address="Brickell Ave",
        identification_type=IdentificationType.PASSPORT,
        identification_number="AB1234567",
        city="Miami",
        country="USA",
        metadata_json={},
    )
    c5 = Customer(
        company_id=company.id,
        first_name="Rosa",
        last_name="Extranjería",
        email=f"rosa.ext@{DEMO_EMAIL_DOMAIN}",
        phone="3007654321",
        identification_type=IdentificationType.CEDULA_EXTRANJERIA,
        identification_number="PE-998877",
        city="Cali",
        country="Colombia",
        metadata_json={},
    )
    c6 = Customer(
        company_id=company.id,
        first_name="Dueño",
        last_name="Original",
        email=f"dueno.original@{DEMO_EMAIL_DOMAIN}",
        phone="3110002233",
        address="Suba",
        identification_type=IdentificationType.CC,
        identification_number="52345678",
        city="Bogotá",
        country="Colombia",
        metadata_json={"relation": "regalo a familiar"},
    )
    session.add_all([c1, c2, c3, c4, c5, c6])
    session.flush()

    sup1 = Supplier(
        company_id=company.id,
        name="Repuestos Andinos SAS",
        contact_person="Luis Proveedor",
        email=f"ventas@repuestos-andinos.{DEMO_EMAIL_DOMAIN}",
        phone="6017778899",
        address="Bodega 12, Mosquera",
        payment_terms="30 días fecha factura",
    )
    sup2 = Supplier(
        company_id=company.id,
        name="Importadora Tech Ltda",
        contact_person="Sandra Compras",
        email=f"compras@import-tech.{DEMO_EMAIL_DOMAIN}",
        phone="6045554433",
        address="Itagüí",
        payment_terms="Contado",
    )
    session.add_all([sup1, sup2])
    session.flush()

    eq1 = Equipment(
        company_id=company.id,
        serial_number="IPH-14PRO-001",
        equipment_type="smartphone",
        brand="Apple",
        model="iPhone 14 Pro",
        imei="359876543210987",
        color="Morado oscuro",
        original_owner_id=c1.id,
        photos_urls=["https://example.com/demo/iphone-front.jpg", "https://example.com/demo/iphone-back.jpg"],
        additional_notes="Caja y cargador originales",
        first_received_date=utc_now().date() - timedelta(days=40),
    )
    eq2 = Equipment(
        company_id=company.id,
        serial_number="SGS-S23-002",
        equipment_type="smartphone",
        brand="Samsung",
        model="Galaxy S23",
        imei="354112223344556",
        color="Negro",
        original_owner_id=c2.id,
        photos_urls=[],
        additional_notes="Pantalla con micro-rayón",
    )
    eq3 = Equipment(
        company_id=company.id,
        serial_number="HP-PAV-003",
        equipment_type="laptop",
        brand="HP",
        model="Pavilion 15",
        imei=None,
        color="Plata",
        original_owner_id=None,
        photos_urls=[],
        additional_notes="Sin disco SSD al ingreso",
    )
    eq4 = Equipment(
        company_id=company.id,
        serial_number="MAC-AIR-M2-004",
        equipment_type="laptop",
        brand="Apple",
        model="MacBook Air M2",
        imei=None,
        color="Midnight",
        original_owner_id=c4.id,
        photos_urls=[],
        additional_notes="AppleCare hasta 2025",
    )
    eq5 = Equipment(
        company_id=company.id,
        serial_number="TAB-S9-005",
        equipment_type="tablet",
        brand="Samsung",
        model="Tab S9",
        imei=None,
        color="Beige",
        original_owner_id=c5.id,
        photos_urls=[],
        additional_notes="S Pen incluido",
    )
    eq6 = Equipment(
        company_id=company.id,
        serial_number="XIA-13T-006",
        equipment_type="smartphone",
        brand="Xiaomi",
        model="13T",
        imei="356998877665544",
        color="Verde",
        original_owner_id=c3.id,
        photos_urls=[],
        additional_notes="Dual SIM",
    )
    eq7 = Equipment(
        company_id=company.id,
        serial_number="LEN-LEGION-007",
        equipment_type="laptop",
        brand="Lenovo",
        model="Legion 5",
        imei=None,
        color="Negro",
        original_owner_id=None,
        photos_urls=[],
        additional_notes="Gaming, ventiladores ruidosos",
    )
    eq8 = Equipment(
        company_id=company.id,
        serial_number="PS5-DISC-008",
        equipment_type="consola",
        brand="Sony",
        model="PlayStation 5",
        imei=None,
        color="Blanco",
        original_owner_id=c6.id,
        photos_urls=[],
        additional_notes="Lector disco atascado intermitente",
    )
    session.add_all([eq1, eq2, eq3, eq4, eq5, eq6, eq7, eq8])
    session.flush()

    inv_screen = InventoryItem(
        company_id=company.id,
        item_type="repuesto",
        sku="REP-PANT-IPH14",
        name="Pantalla iPhone 14 Pro OEM",
        description="Compatible OLED",
        category="Pantallas",
        quantity_stock=Decimal("3"),
        quantity_minimum=Decimal("2"),
        unit_cost=Decimal("450000"),
        unit_price=Decimal("720000"),
        supplier_id=sup1.id,
        photos_urls=[],
        barcode="7701234567890",
        weight=Decimal("0.080"),
        dimensions_json={"w_cm": 14, "h_cm": 6},
        last_restocked_at=utc_now() - timedelta(days=5),
    )
    inv_battery = InventoryItem(
        company_id=company.id,
        item_type="repuesto",
        sku="REP-BAT-S23",
        name="Batería Samsung S23",
        category="Baterías",
        quantity_stock=Decimal("12"),
        quantity_minimum=Decimal("4"),
        unit_cost=Decimal("85000"),
        unit_price=Decimal("165000"),
        supplier_id=sup1.id,
        photos_urls=[],
        barcode="7709988776655",
        weight=Decimal("0.055"),
        dimensions_json={},
    )
    inv_ssd = InventoryItem(
        company_id=company.id,
        item_type="repuesto",
        sku="SSD-NVME-1TB",
        name="SSD NVMe 1TB",
        category="Almacenamiento",
        quantity_stock=Decimal("25"),
        quantity_minimum=Decimal("5"),
        unit_cost=Decimal("280000"),
        unit_price=Decimal("420000"),
        supplier_id=sup2.id,
        photos_urls=[],
        barcode="7890123456789",
        weight=Decimal("0.010"),
        dimensions_json={},
    )
    inv_low = InventoryItem(
        company_id=company.id,
        item_type="consumible",
        sku="ALC-IPA-1L",
        name="Alcohol isopropílico 1L",
        category="Laboratorio",
        quantity_stock=Decimal("1"),
        quantity_minimum=Decimal("3"),
        unit_cost=Decimal("12000"),
        unit_price=Decimal("22000"),
        supplier_id=sup2.id,
        photos_urls=[],
        barcode=None,
        weight=Decimal("1.0"),
        dimensions_json={},
    )
    inv_tool = InventoryItem(
        company_id=company.id,
        item_type="herramienta",
        sku="KIT-TRI-001",
        name="Kit destornilladores Torx",
        category="Herramientas",
        quantity_stock=Decimal("8"),
        quantity_minimum=Decimal("2"),
        unit_cost=Decimal("45000"),
        unit_price=Decimal("89000"),
        supplier_id=sup1.id,
        photos_urls=[],
        barcode="7701112223334",
        weight=Decimal("0.350"),
        dimensions_json={},
    )
    inv_case = InventoryItem(
        company_id=company.id,
        item_type="accesorio",
        sku="FUNDA-UNIV-L",
        name="Funda universal talla L",
        category="Accesorios",
        quantity_stock=Decimal("40"),
        quantity_minimum=Decimal("10"),
        unit_cost=Decimal("8000"),
        unit_price=Decimal("19900"),
        supplier_id=sup2.id,
        photos_urls=[],
        barcode=None,
        weight=Decimal("0.120"),
        dimensions_json={},
    )
    session.add_all([inv_screen, inv_battery, inv_ssd, inv_low, inv_tool, inv_case])
    session.flush()

    session.add_all(
        [
            InventoryMovement(
                inventory_item_id=inv_ssd.id,
                movement_type=InventoryMovementType.PURCHASE,
                quantity_change=Decimal("10"),
                service_order_id=None,
                notes="Compra inicial demo",
                moved_by_id=admin.id,
            ),
            InventoryMovement(
                inventory_item_id=inv_low.id,
                movement_type=InventoryMovementType.ADJUSTMENT,
                quantity_change=Decimal("-2"),
                service_order_id=None,
                notes="Ajuste inventario físico",
                moved_by_id=recep.id,
            ),
            InventoryMovement(
                inventory_item_id=inv_battery.id,
                movement_type=InventoryMovementType.DAMAGE,
                quantity_change=Decimal("-1"),
                service_order_id=None,
                notes="Unidad dañada en bodega",
                moved_by_id=tech1.id,
            ),
        ]
    )

    def mk_order(
        num: int,
        equipment: Equipment,
        customer: Customer,
        status: OrderStatus,
        priority: OrderPriority,
        assigned,
        problem: str,
        diagnosis: str | None,
        parts: Decimal,
        labor: Decimal,
        original_owner=None,
        days_ago: int = 0,
    ) -> ServiceOrder:
        on = f"ORD-{num:06d}"
        total = parts + labor
        so = ServiceOrder(
            company_id=company.id,
            order_number=on,
            equipment_id=equipment.id,
            current_customer_id=customer.id,
            original_owner_id=original_owner.id if original_owner else None,
            status=status,
            priority=priority,
            assigned_to_id=assigned.id if assigned else None,
            problem_description=problem,
            diagnosis_notes=diagnosis,
            estimated_completion=utc_now() + timedelta(days=3) if status not in (OrderStatus.DELIVERED, OrderStatus.CANCELLED) else None,
            actual_completion=utc_now() - timedelta(days=1)
            if status in (OrderStatus.COMPLETED, OrderStatus.DELIVERED)
            else None,
            cost_parts=parts,
            cost_labor=labor,
            total_cost=total,
            created_by_id=recep.id,
        )
        if days_ago:
            so.created_at = utc_now() - timedelta(days=days_ago)
            so.updated_at = so.created_at
        return so

    orders = [
        mk_order(
            1,
            eq1,
            c1,
            OrderStatus.RECEIVED,
            OrderPriority.MEDIUM,
            None,
            "No carga después de actualización iOS.",
            None,
            Decimal("0"),
            Decimal("0"),
            days_ago=1,
        ),
        mk_order(
            2,
            eq2,
            c2,
            OrderStatus.DIAGNOSING,
            OrderPriority.HIGH,
            tech1,
            "Se apaga solo con cámara abierta.",
            "Posible fallo PMIC; stress test GPU.",
            Decimal("0"),
            Decimal("50000"),
            days_ago=3,
        ),
        mk_order(
            3,
            eq3,
            c3,
            OrderStatus.WAITING_PARTS,
            OrderPriority.URGENT,
            tech2,
            "No enciende, olor a quemado cerca de VRM.",
            "Falta repuesto placa madre HP; cotizado.",
            Decimal("120000"),
            Decimal("80000"),
            days_ago=5,
        ),
        mk_order(
            4,
            eq4,
            c4,
            OrderStatus.IN_REPAIR,
            OrderPriority.MEDIUM,
            tech1,
            "Teclas F1-F4 intermitentes.",
            "Limpieza flex y reball parcial.",
            Decimal("35000"),
            Decimal("120000"),
            days_ago=7,
        ),
        mk_order(
            5,
            eq5,
            c5,
            OrderStatus.COMPLETED,
            OrderPriority.LOW,
            tech2,
            "Cristal táctil con fantasmas.",
            "Reemplazo digitalizador OK.",
            Decimal("210000"),
            Decimal("95000"),
            days_ago=10,
        ),
        mk_order(
            6,
            eq6,
            c1,
            OrderStatus.DELIVERED,
            OrderPriority.MEDIUM,
            tech1,
            "Micrófono con ruido de fondo.",
            "Reemplazo flex mic.",
            Decimal("45000"),
            Decimal("70000"),
            days_ago=14,
        ),
        mk_order(
            7,
            eq7,
            c2,
            OrderStatus.CANCELLED,
            OrderPriority.LOW,
            None,
            "Cliente desistió por costo de reparación.",
            "Presupuesto rechazado por cliente.",
            Decimal("0"),
            Decimal("30000"),
            days_ago=20,
        ),
        mk_order(
            8,
            eq8,
            c1,
            OrderStatus.IN_REPAIR,
            OrderPriority.URGENT,
            tech1,
            "Lector disco no extrae; juego atascado.",
            "Desmontaje mecanismo en curso.",
            Decimal("0"),
            Decimal("60000"),
            original_owner=c6,
            days_ago=2,
        ),
    ]
    session.add_all(orders)
    session.flush()

    sync_cost_lines_from_order_aggregates(session, company.id, orders, start_index=1)

    # Timeline de ejemplo en una orden con historial
    o_hist = orders[1]
    session.add_all(
        [
            ServiceOrderTimeline(
                service_order_id=o_hist.id,
                old_status=None,
                new_status=OrderStatus.RECEIVED.value,
                changed_by_id=recep.id,
                notes="Ingreso en recepción",
                time_spent_seconds=None,
            ),
            ServiceOrderTimeline(
                service_order_id=o_hist.id,
                old_status=OrderStatus.RECEIVED.value,
                new_status=OrderStatus.DIAGNOSING.value,
                changed_by_id=tech1.id,
                notes="Asignado a diagnóstico",
                time_spent_seconds=1800,
            ),
        ]
    )

    # Movimiento de inventario ligado a orden (repuesto usado en reparación simulada)
    session.add(
        InventoryMovement(
            inventory_item_id=inv_tool.id,
            movement_type=InventoryMovementType.USED_IN_REPAIR,
            quantity_change=Decimal("-1"),
            service_order_id=orders[4].id,
            notes="Uso de kit Torx en reparación Tab S9",
            moved_by_id=tech2.id,
        )
    )

    session.add(
        PDFDocument(
            company_id=company.id,
            service_order_id=orders[5].id,
            document_type="delivery_receipt",
            file_url="https://example.com/demo/pdf/entrega-ORD-000006.pdf",
            generated_by_id=recep.id,
        )
    )

    apply_primary_extended_scenarios(
        session,
        company=company,
        orders=orders,
        admin=admin,
        recep=recep,
        tech1=tech1,
        tech2=tech2,
        inv_battery=inv_battery,
        inv_case=inv_case,
    )

    company.next_order_number = max(company.next_order_number, 50)
    return company
