"""Dataset demo del taller principal — dataset amplio, cubre todos los módulos 1-a-1."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.dt import utc_now
from app.core.enums import (
    ContractKind,
    CostLineCategory,
    IdentificationType,
    InventoryMovementType,
    OrderPriority,
    OrderStatus,
    RoleChangeStatus,
    ServiceOrderKind,
    UserRole,
)
from app.db.models.audit_log import AuditLog
from app.db.models.company import Company
from app.db.models.customer import Customer
from app.db.models.customer_portal_user import CustomerPortalUser
from app.db.models.equipment import Equipment, EquipmentAttribute
from app.db.models.inventory import InventoryItem, InventoryMovement
from app.db.models.inventory_category import InventoryCategory
from app.db.models.field_report import FieldReport
from app.db.models.pdf_document import PDFDocument
from app.db.models.rbac import RoleChangeRequest, TemporaryPermission
from app.db.models.service_contract import ServiceContract
from app.db.models.service_order import ServiceOrder, ServiceOrderCostLine, ServiceOrderTimeline
from app.db.models.supplier import Supplier
from app.db.models.user import User
from scripts.seed_demo_constants import DEMO_EMAIL_DOMAIN, DEMO_NIT
from scripts.seed_demo_rbac import apply_demo_company_plan, ensure_demo_sites_primary
from scripts.seed_demo_scenarios import apply_primary_extended_scenarios, sync_cost_lines_from_order_aggregates


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _order(
    company_id,
    order_number: str,
    equipment: Equipment,
    customer: Customer,
    status: OrderStatus,
    priority: OrderPriority,
    assigned_to: User | None,
    problem: str,
    diagnosis: str | None,
    cost_parts: Decimal,
    cost_labor: Decimal,
    created_by: User,
    site=None,
    original_owner: Customer | None = None,
    order_kind: ServiceOrderKind = ServiceOrderKind.WORKSHOP_INTAKE,
    days_ago: int = 0,
    service_contract=None,
) -> ServiceOrder:
    total = cost_parts + cost_labor
    now = utc_now()
    created = now - timedelta(days=days_ago)
    actual_completion = (
        now - timedelta(days=max(0, days_ago - 1))
        if status in (OrderStatus.COMPLETED, OrderStatus.DELIVERED)
        else None
    )
    estimated = (
        now + timedelta(days=3)
        if status not in (OrderStatus.DELIVERED, OrderStatus.CANCELLED, OrderStatus.COMPLETED)
        else None
    )
    so = ServiceOrder(
        company_id=company_id,
        order_number=order_number,
        equipment_id=equipment.id,
        current_customer_id=customer.id,
        original_owner_id=original_owner.id if original_owner else None,
        status=status,
        priority=priority,
        assigned_to_id=assigned_to.id if assigned_to else None,
        problem_description=problem,
        diagnosis_notes=diagnosis,
        estimated_completion=estimated,
        actual_completion=actual_completion,
        cost_parts=cost_parts,
        cost_labor=cost_labor,
        total_cost=total,
        created_by_id=created_by.id,
        order_kind=order_kind,
        site_id=site.id if site else None,
        service_contract_id=service_contract.id if service_contract else None,
    )
    so.created_at = created
    so.updated_at = created
    return so


def _timeline_entry(order: ServiceOrder, old_s, new_s, actor: User, notes: str, seconds: int | None = None):
    return ServiceOrderTimeline(
        service_order_id=order.id,
        old_status=old_s.value if old_s else None,
        new_status=new_s.value,
        changed_by_id=actor.id,
        notes=notes,
        time_spent_seconds=seconds,
    )


def _cost_lines(session: Session, company_id, order: ServiceOrder):
    """Inserta líneas de costo desglosadas y recalcula total."""
    from app.services.order_service import recompute_total_cost
    if order.cost_parts and order.cost_parts > 0:
        session.add(ServiceOrderCostLine(
            company_id=company_id,
            service_order_id=order.id,
            category=CostLineCategory.PARTS,
            description="Repuestos (demo)",
            amount=order.cost_parts,
            sort_order=0,
        ))
    if order.cost_labor and order.cost_labor > 0:
        session.add(ServiceOrderCostLine(
            company_id=company_id,
            service_order_id=order.id,
            category=CostLineCategory.LABOR,
            description="Mano de obra (demo)",
            amount=order.cost_labor,
            sort_order=1,
        ))
    session.flush()
    recompute_total_cost(session, order)


# ---------------------------------------------------------------------------
# Main seed function
# ---------------------------------------------------------------------------

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
    cid = company.id

    # -----------------------------------------------------------------------
    # Usuarios — 10 en total (5 técnicos activos, 2 recepcionistas, 1 admin,
    # 1 viewer, 1 inactivo)
    # -----------------------------------------------------------------------
    admin = User(company_id=cid, email=f"admin@{DEMO_EMAIL_DOMAIN}",
                 full_name="Laura Admin", hashed_password=pwd_hash,
                 role=UserRole.ADMIN, phone="3001110001")
    recep = User(company_id=cid, email=f"recepcion@{DEMO_EMAIL_DOMAIN}",
                 full_name="Carlos Recepción", hashed_password=pwd_hash,
                 role=UserRole.RECEPTION, phone="3001110002")
    recep2 = User(company_id=cid, email=f"recepcion.norte@{DEMO_EMAIL_DOMAIN}",
                  full_name="Sofía Recepción Norte", hashed_password=pwd_hash,
                  role=UserRole.RECEPTION, phone="3001110009")
    tech1 = User(company_id=cid, email=f"tecnico1@{DEMO_EMAIL_DOMAIN}",
                 full_name="María Técnico", hashed_password=pwd_hash,
                 role=UserRole.TECHNICIAN, phone="3001110003")
    tech2 = User(company_id=cid, email=f"tecnico2@{DEMO_EMAIL_DOMAIN}",
                 full_name="Jorge Técnico", hashed_password=pwd_hash,
                 role=UserRole.TECHNICIAN, phone="3001110004")
    tech3 = User(company_id=cid, email=f"tecnico3@{DEMO_EMAIL_DOMAIN}",
                 full_name="Camila Técnico Norte", hashed_password=pwd_hash,
                 role=UserRole.TECHNICIAN, phone="3001110005")
    tech4 = User(company_id=cid, email=f"tecnico4@{DEMO_EMAIL_DOMAIN}",
                 full_name="Andrés Técnico Sur", hashed_password=pwd_hash,
                 role=UserRole.TECHNICIAN, phone="3001110006")
    tech5 = User(company_id=cid, email=f"tecnico5@{DEMO_EMAIL_DOMAIN}",
                 full_name="Felipe Técnico Sur", hashed_password=pwd_hash,
                 role=UserRole.TECHNICIAN, phone="3001110007")
    viewer = User(company_id=cid, email=f"visitante@{DEMO_EMAIL_DOMAIN}",
                  full_name="Ana Solo lectura", hashed_password=pwd_hash,
                  role=UserRole.VIEWER)
    inactive = User(company_id=cid, email=f"baja@{DEMO_EMAIL_DOMAIN}",
                    full_name="Usuario inactivo", hashed_password=pwd_hash,
                    role=UserRole.VIEWER, is_active=False)
    session.add_all([admin, recep, recep2, tech1, tech2, tech3, tech4, tech5, viewer, inactive])
    session.flush()
    for u in [recep, recep2, tech1, tech2, tech3, tech4, tech5, viewer, inactive]:
        u.created_by_id = admin.id
    admin.created_by_id = admin.id

    # -----------------------------------------------------------------------
    # Clientes — 12 perfiles variados
    # -----------------------------------------------------------------------
    c1 = Customer(company_id=cid, first_name="Pedro", last_name="Gómez",
                  email=f"pedro.gomez@{DEMO_EMAIL_DOMAIN}", phone="3101234501",
                  address="Calle 100 # 45", identification_type=IdentificationType.CC,
                  identification_number="1023456789", city="Bogotá", country="Colombia",
                  notes="Prefiere contacto por WhatsApp", metadata_json={"vip": True})
    c2 = Customer(company_id=cid, first_name="Lucía", last_name="Martínez",
                  email=f"lucia.martinez@{DEMO_EMAIL_DOMAIN}", phone="3209876502",
                  address="Av. El Dorado", identification_type=IdentificationType.NIT,
                  identification_number="900555221-1", city="Bogotá", country="Colombia",
                  metadata_json={})
    c3 = Customer(company_id=cid, first_name="Empresa", last_name="Sin email S.A.S.",
                  email=None, phone="6014445566", address="Zona industrial",
                  identification_type=IdentificationType.NIT, identification_number="860001025",
                  city="Medellín", country="Colombia", metadata_json={"billing": "30 días"})
    c4 = Customer(company_id=cid, first_name="John", last_name="Smith",
                  email=f"john.smith@{DEMO_EMAIL_DOMAIN}", phone="+1 305 0001111",
                  address="Brickell Ave", identification_type=IdentificationType.PASSPORT,
                  identification_number="AB1234567", city="Miami", country="USA", metadata_json={})
    c5 = Customer(company_id=cid, first_name="Rosa", last_name="Extranjería",
                  email=f"rosa.ext@{DEMO_EMAIL_DOMAIN}", phone="3007654321",
                  identification_type=IdentificationType.CEDULA_EXTRANJERIA,
                  identification_number="PE-998877", city="Cali", country="Colombia", metadata_json={})
    c6 = Customer(company_id=cid, first_name="Dueño", last_name="Original",
                  email=f"dueno.original@{DEMO_EMAIL_DOMAIN}", phone="3110002233",
                  address="Suba", identification_type=IdentificationType.CC,
                  identification_number="52345678", city="Bogotá", country="Colombia",
                  metadata_json={"relation": "regalo a familiar"})
    c7 = Customer(company_id=cid, first_name="Tecnologías", last_name="del Pacífico S.A.S.",
                  email=f"tic.pacifico@{DEMO_EMAIL_DOMAIN}", phone="6024441122",
                  address="Carrera 5 # 20-10", identification_type=IdentificationType.NIT,
                  identification_number="900778833-5", city="Cali", country="Colombia",
                  metadata_json={"sector": "corporativo", "vip": True})
    c8 = Customer(company_id=cid, first_name="Valentina", last_name="Rincón",
                  email=f"valentina.rincon@{DEMO_EMAIL_DOMAIN}", phone="3156667788",
                  identification_type=IdentificationType.CC, identification_number="1045678901",
                  city="Medellín", country="Colombia", metadata_json={})
    c9 = Customer(company_id=cid, first_name="Cooperativa", last_name="Sur Ltda",
                  email=f"coop.sur@{DEMO_EMAIL_DOMAIN}", phone="6015559900",
                  identification_type=IdentificationType.NIT, identification_number="830445566-1",
                  city="Bogotá", country="Colombia", metadata_json={"zona": "Sur"})
    c10 = Customer(company_id=cid, first_name="Rodrigo", last_name="Peña",
                   email=f"rodrigo.pena@{DEMO_EMAIL_DOMAIN}", phone="3102223344",
                   identification_type=IdentificationType.CC, identification_number="80334455",
                   city="Bogotá", country="Colombia", metadata_json={})
    c11 = Customer(company_id=cid, first_name="Importadora", last_name="Andina SAS",
                   email=f"imp.andina@{DEMO_EMAIL_DOMAIN}", phone="6012225566",
                   identification_type=IdentificationType.NIT, identification_number="900223344-8",
                   city="Bogotá", country="Colombia", metadata_json={"contrato": True})
    c12 = Customer(company_id=cid, first_name="Sebastián", last_name="Mora",
                   email=f"sebastian.mora@{DEMO_EMAIL_DOMAIN}", phone="3178889900",
                   identification_type=IdentificationType.CC, identification_number="1067234567",
                   city="Bogotá", country="Colombia", metadata_json={})
    session.add_all([c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11, c12])
    session.flush()

    # -----------------------------------------------------------------------
    # Proveedores — 3
    # -----------------------------------------------------------------------
    sup1 = Supplier(company_id=cid, name="Repuestos Andinos SAS",
                    contact_person="Luis Proveedor",
                    email=f"ventas@repuestos-andinos.{DEMO_EMAIL_DOMAIN}",
                    phone="6017778899", address="Bodega 12, Mosquera",
                    payment_terms="30 días fecha factura")
    sup2 = Supplier(company_id=cid, name="Importadora Tech Ltda",
                    contact_person="Sandra Compras",
                    email=f"compras@import-tech.{DEMO_EMAIL_DOMAIN}",
                    phone="6045554433", address="Itagüí", payment_terms="Contado")
    sup3 = Supplier(company_id=cid, name="Distribuidora Sur Colombia",
                    contact_person="Hernán Logística",
                    email=f"logistica@dist-sur.{DEMO_EMAIL_DOMAIN}",
                    phone="6023336677", address="Zona Franca Bogotá",
                    payment_terms="15 días")
    session.add_all([sup1, sup2, sup3])
    session.flush()

    # -----------------------------------------------------------------------
    # Equipos — 16 dispositivos variados
    # -----------------------------------------------------------------------
    eq1 = Equipment(company_id=cid, serial_number="IPH-14PRO-001",
                    equipment_type="smartphone", brand="Apple", model="iPhone 14 Pro",
                    imei="359876543210987", color="Morado oscuro",
                    original_owner_id=c1.id,
                    photos_urls=["https://example.com/demo/iphone-front.jpg"],
                    additional_notes="Caja y cargador originales",
                    first_received_date=utc_now().date() - timedelta(days=40))
    eq2 = Equipment(company_id=cid, serial_number="SGS-S23-002",
                    equipment_type="smartphone", brand="Samsung", model="Galaxy S23",
                    imei="354112223344556", color="Negro",
                    original_owner_id=c2.id, photos_urls=[],
                    additional_notes="Pantalla con micro-rayón")
    eq3 = Equipment(company_id=cid, serial_number="HP-PAV-003",
                    equipment_type="laptop", brand="HP", model="Pavilion 15",
                    color="Plata", original_owner_id=None, photos_urls=[],
                    additional_notes="Sin disco SSD al ingreso")
    eq4 = Equipment(company_id=cid, serial_number="MAC-AIR-M2-004",
                    equipment_type="laptop", brand="Apple", model="MacBook Air M2",
                    color="Midnight", original_owner_id=c4.id, photos_urls=[],
                    additional_notes="AppleCare hasta 2025")
    eq5 = Equipment(company_id=cid, serial_number="TAB-S9-005",
                    equipment_type="tablet", brand="Samsung", model="Tab S9",
                    color="Beige", original_owner_id=c5.id, photos_urls=[],
                    additional_notes="S Pen incluido")
    eq6 = Equipment(company_id=cid, serial_number="XIA-13T-006",
                    equipment_type="smartphone", brand="Xiaomi", model="13T",
                    imei="356998877665544", color="Verde",
                    original_owner_id=c3.id, photos_urls=[],
                    additional_notes="Dual SIM")
    eq7 = Equipment(company_id=cid, serial_number="LEN-LEGION-007",
                    equipment_type="laptop", brand="Lenovo", model="Legion 5",
                    color="Negro", original_owner_id=None, photos_urls=[],
                    additional_notes="Gaming, ventiladores ruidosos")
    eq8 = Equipment(company_id=cid, serial_number="PS5-DISC-008",
                    equipment_type="consola", brand="Sony", model="PlayStation 5",
                    color="Blanco", original_owner_id=c6.id, photos_urls=[],
                    additional_notes="Lector disco atascado intermitente")
    eq9 = Equipment(company_id=cid, serial_number="IPH-15-009",
                    equipment_type="smartphone", brand="Apple", model="iPhone 15",
                    imei="351234567890123", color="Negro",
                    original_owner_id=c7.id, photos_urls=[],
                    additional_notes="Equipo corporativo")
    eq10 = Equipment(company_id=cid, serial_number="SAM-A54-010",
                     equipment_type="smartphone", brand="Samsung", model="Galaxy A54",
                     imei="352233445566778", color="Blanco",
                     original_owner_id=c8.id, photos_urls=[],
                     additional_notes="Pantalla rota borde inferior")
    eq11 = Equipment(company_id=cid, serial_number="DEL-LAT-011",
                     equipment_type="laptop", brand="Dell", model="Latitude 5540",
                     color="Gris", original_owner_id=c9.id, photos_urls=[],
                     additional_notes="Corporativo — sin cargador")
    eq12 = Equipment(company_id=cid, serial_number="ASUS-ZF-012",
                     equipment_type="smartphone", brand="ASUS", model="Zenfone 10",
                     imei="353344556677889", color="Rojo",
                     original_owner_id=c10.id, photos_urls=[],
                     additional_notes="Batería hinchada")
    eq13 = Equipment(company_id=cid, serial_number="HP-ENVY-013",
                     equipment_type="laptop", brand="HP", model="Envy x360",
                     color="Plata", original_owner_id=c11.id, photos_urls=[],
                     additional_notes="Contrato mantenimiento anual",
                     warranty_end=date.today() + timedelta(days=180),
                     warranty_provider="HP Care Pack")
    eq14 = Equipment(company_id=cid, serial_number="NIK-10PRO-014",
                     equipment_type="tablet", brand="Xiaomi", model="Pad 6",
                     color="Gris", original_owner_id=c12.id, photos_urls=[],
                     additional_notes="Cargador rápido incluido")
    eq15 = Equipment(company_id=cid, serial_number="PRN-HP-015",
                     equipment_type="impresora", brand="HP", model="LaserJet M110w",
                     color="Blanco", original_owner_id=c3.id, photos_urls=[],
                     additional_notes="Impresora de oficina, atasco papel frecuente")
    eq16 = Equipment(company_id=cid, serial_number="IPD-PRO-016",
                     equipment_type="tablet", brand="Apple", model="iPad Pro 12.9",
                     color="Plata", original_owner_id=c1.id, photos_urls=[],
                     additional_notes="Lápiz Apple Pencil incluido",
                     warranty_end=date.today() + timedelta(days=90))
    session.add_all([eq1, eq2, eq3, eq4, eq5, eq6, eq7, eq8,
                     eq9, eq10, eq11, eq12, eq13, eq14, eq15, eq16])
    session.flush()

    # Atributos custom en 4 equipos
    session.add_all([
        EquipmentAttribute(equipment_id=eq1.id, key="IMEI secundario", value="359876543210988", type="text"),
        EquipmentAttribute(equipment_id=eq1.id, key="Versión iOS", value="17.4.1", type="text"),
        EquipmentAttribute(equipment_id=eq4.id, key="Versión macOS", value="Sonoma 14.4", type="text"),
        EquipmentAttribute(equipment_id=eq4.id, key="RAM", value="16 GB", type="text"),
        EquipmentAttribute(equipment_id=eq11.id, key="Número activo", value="LAT-5540-C09", type="text"),
        EquipmentAttribute(equipment_id=eq13.id, key="Número contrato HP", value="HP-CP-2024-0089", type="text"),
        EquipmentAttribute(equipment_id=eq13.id, key="Nivel SLA", value="NBD on-site", type="text"),
    ])

    # -----------------------------------------------------------------------
    # Categorías de inventario — 5
    # -----------------------------------------------------------------------
    cat_pantallas = InventoryCategory(company_id=cid, name="Pantallas", color="#3b82f6",
                                       description="Pantallas, digitalizadores y touchscreen")
    cat_baterias = InventoryCategory(company_id=cid, name="Baterías", color="#f59e0b",
                                      description="Baterías originales y compatibles")
    cat_almacenamiento = InventoryCategory(company_id=cid, name="Almacenamiento", color="#8b5cf6",
                                            description="SSD, HDD, tarjetas microSD")
    cat_laboratorio = InventoryCategory(company_id=cid, name="Laboratorio", color="#10b981",
                                         description="Consumibles de taller: limpiadores, adhesivos")
    cat_herramientas = InventoryCategory(company_id=cid, name="Herramientas", color="#ef4444",
                                          description="Destornilladores, pinzas y kits")
    cat_accesorios = InventoryCategory(company_id=cid, name="Accesorios", color="#f97316",
                                        description="Fundas, cables, cargadores genéricos")
    session.add_all([cat_pantallas, cat_baterias, cat_almacenamiento,
                     cat_laboratorio, cat_herramientas, cat_accesorios])
    session.flush()

    # -----------------------------------------------------------------------
    # Inventario — 12 ítems (3 en bajo stock para alertas)
    # -----------------------------------------------------------------------
    inv_screen = InventoryItem(
        company_id=cid, item_type="repuesto", sku="REP-PANT-IPH14",
        name="Pantalla iPhone 14 Pro OEM", description="Compatible OLED",
        category="Pantallas", quantity_stock=Decimal("2"), quantity_minimum=Decimal("3"),
        unit_cost=Decimal("450000"), unit_price=Decimal("720000"),
        supplier_id=sup1.id, barcode="7701234567890",
        weight=Decimal("0.080"), dimensions_json={"w_cm": 14, "h_cm": 6},
        last_restocked_at=utc_now() - timedelta(days=5))
    inv_battery = InventoryItem(
        company_id=cid, item_type="repuesto", sku="REP-BAT-S23",
        name="Batería Samsung S23", category="Baterías",
        quantity_stock=Decimal("12"), quantity_minimum=Decimal("4"),
        unit_cost=Decimal("85000"), unit_price=Decimal("165000"),
        supplier_id=sup1.id, barcode="7709988776655",
        weight=Decimal("0.055"), dimensions_json={})
    inv_ssd = InventoryItem(
        company_id=cid, item_type="repuesto", sku="SSD-NVME-1TB",
        name="SSD NVMe 1TB", category="Almacenamiento",
        quantity_stock=Decimal("8"), quantity_minimum=Decimal("3"),
        unit_cost=Decimal("280000"), unit_price=Decimal("420000"),
        supplier_id=sup2.id, barcode="7890123456789",
        weight=Decimal("0.010"), dimensions_json={})
    inv_low = InventoryItem(
        company_id=cid, item_type="consumible", sku="ALC-IPA-1L",
        name="Alcohol isopropílico 1L", category="Laboratorio",
        quantity_stock=Decimal("3"), quantity_minimum=Decimal("3"),
        unit_cost=Decimal("12000"), unit_price=Decimal("22000"),
        supplier_id=sup2.id, weight=Decimal("1.0"), dimensions_json={})
    inv_tool = InventoryItem(
        company_id=cid, item_type="herramienta", sku="KIT-TRI-001",
        name="Kit destornilladores Torx", category="Herramientas",
        quantity_stock=Decimal("7"), quantity_minimum=Decimal("2"),
        unit_cost=Decimal("45000"), unit_price=Decimal("89000"),
        supplier_id=sup1.id, barcode="7701112223334",
        weight=Decimal("0.350"), dimensions_json={})
    inv_case = InventoryItem(
        company_id=cid, item_type="accesorio", sku="FUNDA-UNIV-L",
        name="Funda universal talla L", category="Accesorios",
        quantity_stock=Decimal("38"), quantity_minimum=Decimal("10"),
        unit_cost=Decimal("8000"), unit_price=Decimal("19900"),
        supplier_id=sup2.id, weight=Decimal("0.120"), dimensions_json={})
    inv_screen_sam = InventoryItem(
        company_id=cid, item_type="repuesto", sku="REP-PANT-SAM-A54",
        name="Pantalla Samsung Galaxy A54", category="Pantallas",
        quantity_stock=Decimal("4"), quantity_minimum=Decimal("2"),
        unit_cost=Decimal("210000"), unit_price=Decimal("350000"),
        supplier_id=sup1.id, barcode="7701234500001",
        weight=Decimal("0.075"), dimensions_json={"w_cm": 15, "h_cm": 7})
    inv_bat_apple = InventoryItem(
        company_id=cid, item_type="repuesto", sku="REP-BAT-IPH14",
        name="Batería iPhone 14 Pro", category="Baterías",
        quantity_stock=Decimal("1"), quantity_minimum=Decimal("4"),
        unit_cost=Decimal("120000"), unit_price=Decimal("220000"),
        supplier_id=sup1.id, weight=Decimal("0.044"), dimensions_json={})
    inv_hdd = InventoryItem(
        company_id=cid, item_type="repuesto", sku="HDD-SATA-500",
        name="HDD SATA 500 GB 2.5\"", category="Almacenamiento",
        quantity_stock=Decimal("5"), quantity_minimum=Decimal("2"),
        unit_cost=Decimal("85000"), unit_price=Decimal("150000"),
        supplier_id=sup3.id, weight=Decimal("0.095"), dimensions_json={})
    inv_pasta = InventoryItem(
        company_id=cid, item_type="consumible", sku="PASTA-TERM-5G",
        name="Pasta térmica premium 5g", category="Laboratorio",
        quantity_stock=Decimal("15"), quantity_minimum=Decimal("5"),
        unit_cost=Decimal("9000"), unit_price=Decimal("18000"),
        supplier_id=sup2.id, weight=Decimal("0.010"), dimensions_json={})
    inv_cable = InventoryItem(
        company_id=cid, item_type="accesorio", sku="CABLE-USBC-1M",
        name="Cable USB-C 1m reforzado", category="Accesorios",
        quantity_stock=Decimal("20"), quantity_minimum=Decimal("5"),
        unit_cost=Decimal("12000"), unit_price=Decimal("25000"),
        supplier_id=sup3.id, weight=Decimal("0.060"), dimensions_json={})
    inv_pantalla_mac = InventoryItem(
        company_id=cid, item_type="repuesto", sku="REP-LCD-MACAIR",
        name="Pantalla MacBook Air M2 Liquid Retina", category="Pantallas",
        quantity_stock=Decimal("1"), quantity_minimum=Decimal("1"),
        unit_cost=Decimal("1200000"), unit_price=Decimal("1850000"),
        supplier_id=sup2.id, weight=Decimal("0.450"), dimensions_json={})
    session.add_all([inv_screen, inv_battery, inv_ssd, inv_low, inv_tool, inv_case,
                     inv_screen_sam, inv_bat_apple, inv_hdd, inv_pasta, inv_cable, inv_pantalla_mac])
    session.flush()

    # Movimientos iniciales de inventario
    session.add_all([
        InventoryMovement(inventory_item_id=inv_ssd.id,
                          movement_type=InventoryMovementType.PURCHASE,
                          quantity_change=Decimal("10"), notes="Compra inicial demo",
                          moved_by_id=admin.id),
        InventoryMovement(inventory_item_id=inv_low.id,
                          movement_type=InventoryMovementType.ADJUSTMENT,
                          quantity_change=Decimal("-1"), notes="Ajuste inventario físico",
                          moved_by_id=recep.id),
        InventoryMovement(inventory_item_id=inv_battery.id,
                          movement_type=InventoryMovementType.DAMAGE,
                          quantity_change=Decimal("-1"), notes="Unidad dañada en bodega",
                          moved_by_id=tech1.id),
        InventoryMovement(inventory_item_id=inv_screen.id,
                          movement_type=InventoryMovementType.PURCHASE,
                          quantity_change=Decimal("5"), notes="Compra proveedor — reposición",
                          moved_by_id=admin.id),
        InventoryMovement(inventory_item_id=inv_battery.id,
                          movement_type=InventoryMovementType.ADJUSTMENT,
                          quantity_change=Decimal("3"), notes="Ajuste conteo físico",
                          moved_by_id=recep.id),
        InventoryMovement(inventory_item_id=inv_hdd.id,
                          movement_type=InventoryMovementType.PURCHASE,
                          quantity_change=Decimal("5"), notes="Compra inicial HDD",
                          moved_by_id=admin.id),
        InventoryMovement(inventory_item_id=inv_pasta.id,
                          movement_type=InventoryMovementType.PURCHASE,
                          quantity_change=Decimal("20"), notes="Compra pasta térmica",
                          moved_by_id=recep.id),
    ])

    # -----------------------------------------------------------------------
    # SEDES (necesitamos las referencias antes de crear órdenes)
    # -----------------------------------------------------------------------
    apply_demo_company_plan(session, company)
    principal, norte, sur = ensure_demo_sites_primary(
        session, company,
        admin=admin, recep=recep, recep2=recep2,
        tech1=tech1, tech2=tech2, tech3=tech3, tech4=tech4, tech5=tech5,
        viewer=viewer, inactive=inactive,
    )

    # -----------------------------------------------------------------------
    # ÓRDENES ACTIVAS — distribuidas por sede y técnico (15 órdenes)
    # Cada técnico tiene al menos 3 órdenes activas para que el panel de carga
    # muestre datos reales.
    # -----------------------------------------------------------------------
    num = [1]

    def next_num():
        n = f"ORD-{num[0]:06d}"
        num[0] += 1
        return n

    # --- Sede Principal: tech1 (4 órdenes activas) ---
    o1 = _order(cid, next_num(), eq1, c1, OrderStatus.RECEIVED, OrderPriority.MEDIUM,
                tech1, "No carga después de actualización iOS.", None,
                Decimal("0"), Decimal("0"), recep, site=principal, days_ago=1)
    o2 = _order(cid, next_num(), eq2, c2, OrderStatus.DIAGNOSING, OrderPriority.HIGH,
                tech1, "Se apaga solo con cámara abierta.",
                "Posible fallo PMIC; stress test GPU.",
                Decimal("0"), Decimal("50000"), recep, site=principal, days_ago=3)
    o3 = _order(cid, next_num(), eq4, c4, OrderStatus.IN_REPAIR, OrderPriority.MEDIUM,
                tech1, "Teclas F1-F4 intermitentes.",
                "Limpieza flex y reball parcial.",
                Decimal("35000"), Decimal("120000"), recep, site=principal, days_ago=7)
    o4 = _order(cid, next_num(), eq16, c1, OrderStatus.WAITING_PARTS, OrderPriority.HIGH,
                tech1, "Pantalla con manchas permanentes tras caída.",
                "Requiere panel Liquid Retina; cotizando.",
                Decimal("0"), Decimal("80000"), recep, site=principal, days_ago=4)

    # --- Sede Principal: tech2 (3 órdenes activas) ---
    o5 = _order(cid, next_num(), eq3, c3, OrderStatus.WAITING_PARTS, OrderPriority.URGENT,
                tech2, "No enciende, olor a quemado cerca de VRM.",
                "Falta repuesto placa madre HP; cotizado.",
                Decimal("120000"), Decimal("80000"), recep, site=principal, days_ago=5)
    o6 = _order(cid, next_num(), eq8, c1, OrderStatus.IN_REPAIR, OrderPriority.URGENT,
                tech2, "Lector disco no extrae; juego atascado.",
                "Desmontaje mecanismo en curso.",
                Decimal("0"), Decimal("60000"), recep, site=principal,
                original_owner=c6, days_ago=2)
    o7 = _order(cid, next_num(), eq10, c8, OrderStatus.DIAGNOSING, OrderPriority.MEDIUM,
                tech2, "Pantalla rota en esquina inferior derecha.",
                "Revisando digitalizador y marco.",
                Decimal("0"), Decimal("40000"), recep, site=principal, days_ago=2)

    # --- Sede Norte: tech3 (3 órdenes activas) ---
    o8 = _order(cid, next_num(), eq9, c7, OrderStatus.RECEIVED, OrderPriority.HIGH,
                tech3, "Batería no carga más del 20%.", None,
                Decimal("0"), Decimal("0"), recep2, site=norte, days_ago=1)
    o9 = _order(cid, next_num(), eq12, c10, OrderStatus.IN_REPAIR, OrderPriority.HIGH,
                tech3, "Batería hinchada — riesgo de seguridad.",
                "Reemplazo de batería en proceso.",
                Decimal("120000"), Decimal("55000"), recep2, site=norte, days_ago=3)
    o10 = _order(cid, next_num(), eq14, c12, OrderStatus.DIAGNOSING, OrderPriority.LOW,
                 tech3, "Táctil con respuesta errática.",
                 "Revisión flex y firmware.",
                 Decimal("0"), Decimal("35000"), recep2, site=norte, days_ago=4)

    # --- Sede Norte: tech2 (2 órdenes activas — multi-sede) ---
    o11 = _order(cid, next_num(), eq15, c3, OrderStatus.RECEIVED, OrderPriority.MEDIUM,
                 tech2, "Atasco de papel al imprimir doble faz.", None,
                 Decimal("0"), Decimal("0"), recep2, site=norte, days_ago=0)
    o12 = _order(cid, next_num(), eq6, c3, OrderStatus.WAITING_PARTS, OrderPriority.MEDIUM,
                 tech2, "Conector de carga defectuoso.",
                 "Esperando flex de carga Xiaomi 13T.",
                 Decimal("35000"), Decimal("45000"), recep2, site=norte, days_ago=6)

    # --- Sede Sur: tech4 (3 órdenes activas) ---
    o13 = _order(cid, next_num(), eq11, c9, OrderStatus.IN_REPAIR, OrderPriority.URGENT,
                 tech4, "No enciende, no carga — daño por líquido.",
                 "Limpieza ultrasónica en progreso.",
                 Decimal("95000"), Decimal("150000"), recep, site=sur, days_ago=2)
    o14 = _order(cid, next_num(), eq13, c11, OrderStatus.DIAGNOSING, OrderPriority.HIGH,
                 tech4, "Teclado teclas bloqueadas — garantía HP Care Pack.",
                 "Diagnóstico bajo contrato mantenimiento.",
                 Decimal("0"), Decimal("60000"), recep, site=sur,
                 order_kind=ServiceOrderKind.WORKSHOP_INTAKE_CONTRACT, days_ago=1)
    o15 = _order(cid, next_num(), eq5, c5, OrderStatus.RECEIVED, OrderPriority.LOW,
                 tech4, "S Pen no responde en esquina superior.", None,
                 Decimal("0"), Decimal("0"), recep, site=sur, days_ago=0)

    # --- Sede Sur: tech5 (3 órdenes activas) ---
    o16 = _order(cid, next_num(), eq7, c2, OrderStatus.DIAGNOSING, OrderPriority.MEDIUM,
                 tech5, "Ventiladores ruidosos al cargar juegos.",
                 "Revisión de sistema de refrigeración.",
                 Decimal("0"), Decimal("70000"), recep, site=sur, days_ago=3)
    o17 = _order(cid, next_num(), eq9, c7, OrderStatus.WAITING_PARTS, OrderPriority.HIGH,
                 tech5, "Conector MagSafe doblado — sin carga.",
                 "Cotizando conector con proveedor.",
                 Decimal("65000"), Decimal("80000"), recep, site=sur, days_ago=5)
    o18 = _order(cid, next_num(), eq3, c3, OrderStatus.IN_REPAIR, OrderPriority.MEDIUM,
                 tech5, "SSD no detectado tras formateo.",
                 "Reemplazo de SSD NVMe en curso.",
                 Decimal("280000"), Decimal("60000"), recep, site=sur, days_ago=4)
    o19 = _order(cid, next_num(), eq5, c5, OrderStatus.RECEIVED, OrderPriority.MEDIUM,
                 None, "S Pen no responde — pendiente asignación de técnico.", None,
                 Decimal("0"), Decimal("0"), recep, site=norte, days_ago=0)

    active_orders = [o1, o2, o3, o4, o5, o6, o7, o8, o9, o10,
                     o11, o12, o13, o14, o15, o16, o17, o18, o19]
    session.add_all(active_orders)
    session.flush()

    # -----------------------------------------------------------------------
    # ÓRDENES HISTÓRICAS — 25 órdenes completadas/entregadas en los últimos
    # 12 meses para el gráfico de revenue mensual.
    # Distribuidas ~2-3 por mes con costos variados.
    # -----------------------------------------------------------------------
    history_specs = [
        # (days_ago_created, days_ago_completed, customer, equipment, tech, priority,
        #   cost_parts, cost_labor, status, site)
        (360, 358, c1, eq1, tech1, OrderPriority.MEDIUM,   Decimal("450000"), Decimal("120000"), OrderStatus.DELIVERED,  principal),
        (355, 352, c2, eq2, tech2, OrderPriority.HIGH,     Decimal("85000"),  Decimal("95000"),  OrderStatus.DELIVERED,  principal),
        (330, 327, c3, eq3, tech1, OrderPriority.URGENT,   Decimal("320000"), Decimal("180000"), OrderStatus.COMPLETED,  principal),
        (320, 318, c7, eq9, tech3, OrderPriority.HIGH,     Decimal("210000"), Decimal("130000"), OrderStatus.DELIVERED,  norte),
        (300, 298, c4, eq4, tech1, OrderPriority.MEDIUM,   Decimal("35000"),  Decimal("120000"), OrderStatus.DELIVERED,  principal),
        (295, 293, c9, eq11, tech4, OrderPriority.URGENT,  Decimal("580000"), Decimal("250000"), OrderStatus.DELIVERED,  sur),
        (270, 268, c5, eq5, tech2, OrderPriority.LOW,      Decimal("210000"), Decimal("95000"),  OrderStatus.DELIVERED,  principal),
        (265, 263, c8, eq10, tech3, OrderPriority.MEDIUM,  Decimal("180000"), Decimal("70000"),  OrderStatus.COMPLETED,  norte),
        (240, 238, c10, eq12, tech5, OrderPriority.HIGH,   Decimal("120000"), Decimal("55000"),  OrderStatus.DELIVERED,  sur),
        (235, 233, c11, eq13, tech4, OrderPriority.HIGH,   Decimal("0"),      Decimal("180000"), OrderStatus.COMPLETED,  sur),
        (210, 208, c1, eq16, tech1, OrderPriority.MEDIUM,  Decimal("0"),      Decimal("85000"),  OrderStatus.DELIVERED,  principal),
        (205, 202, c2, eq7, tech2, OrderPriority.LOW,      Decimal("0"),      Decimal("60000"),  OrderStatus.COMPLETED,  principal),
        (180, 178, c12, eq14, tech3, OrderPriority.MEDIUM, Decimal("75000"),  Decimal("50000"),  OrderStatus.DELIVERED,  norte),
        (175, 173, c3, eq15, tech2, OrderPriority.LOW,     Decimal("45000"),  Decimal("40000"),  OrderStatus.DELIVERED,  norte),
        (150, 148, c7, eq9, tech5, OrderPriority.HIGH,     Decimal("210000"), Decimal("130000"), OrderStatus.DELIVERED,  sur),
        (145, 143, c4, eq4, tech1, OrderPriority.MEDIUM,   Decimal("120000"), Decimal("90000"),  OrderStatus.DELIVERED,  principal),
        (120, 118, c9, eq11, tech4, OrderPriority.URGENT,  Decimal("480000"), Decimal("200000"), OrderStatus.COMPLETED,  sur),
        (115, 113, c2, eq2, tech2, OrderPriority.HIGH,     Decimal("85000"),  Decimal("75000"),  OrderStatus.DELIVERED,  principal),
        (90,  88,  c11, eq13, tech5, OrderPriority.HIGH,   Decimal("0"),      Decimal("150000"), OrderStatus.DELIVERED,  sur),
        (85,  83,  c5, eq5, tech3, OrderPriority.MEDIUM,   Decimal("210000"), Decimal("95000"),  OrderStatus.DELIVERED,  norte),
        (60,  58,  c1, eq1, tech1, OrderPriority.MEDIUM,   Decimal("220000"), Decimal("80000"),  OrderStatus.DELIVERED,  principal),
        (55,  53,  c8, eq10, tech3, OrderPriority.HIGH,    Decimal("180000"), Decimal("70000"),  OrderStatus.COMPLETED,  norte),
        (30,  28,  c10, eq12, tech4, OrderPriority.MEDIUM, Decimal("120000"), Decimal("55000"),  OrderStatus.DELIVERED,  sur),
        (25,  23,  c7, eq9, tech2, OrderPriority.HIGH,     Decimal("150000"), Decimal("90000"),  OrderStatus.DELIVERED,  principal),
        (10,   8,  c12, eq6, tech5, OrderPriority.LOW,     Decimal("35000"),  Decimal("45000"),  OrderStatus.COMPLETED,  sur),
    ]

    history_orders = []
    for spec in history_specs:
        da_c, da_comp, cust, eq, tech, prio, cp, cl, st, site_ref = spec
        problem = f"Reparación completada — referencia histórica demo."
        diagnosis = "Diagnóstico y reparación realizados satisfactoriamente."
        so = _order(cid, next_num(), eq, cust, st, prio, tech,
                    problem, diagnosis, cp, cl, recep, site=site_ref, days_ago=da_c)
        now = utc_now()
        so.actual_completion = now - timedelta(days=da_comp)
        history_orders.append(so)

    # 3 canceladas para completar distribución de estados
    cancelled_orders = [
        _order(cid, next_num(), eq7, c2, OrderStatus.CANCELLED, OrderPriority.LOW,
               None, "Cliente desistió por costo de reparación.",
               "Presupuesto rechazado por cliente.",
               Decimal("0"), Decimal("30000"), recep, site=principal, days_ago=20),
        _order(cid, next_num(), eq15, c3, OrderStatus.CANCELLED, OrderPriority.LOW,
               None, "Impresora sin repuesto — obsoleta.",
               "Sin soporte técnico disponible.",
               Decimal("0"), Decimal("0"), recep2, site=norte, days_ago=35),
        _order(cid, next_num(), eq14, c12, OrderStatus.CANCELLED, OrderPriority.MEDIUM,
               None, "Cliente recogió el equipo sin reparar.",
               None, Decimal("0"), Decimal("0"), recep, site=sur, days_ago=15),
    ]

    session.add_all(history_orders + cancelled_orders)
    session.flush()

    # -----------------------------------------------------------------------
    # Líneas de costo en todas las órdenes
    # -----------------------------------------------------------------------
    all_orders_with_cost = active_orders + history_orders + cancelled_orders
    for o in all_orders_with_cost:
        _cost_lines(session, cid, o)

    # -----------------------------------------------------------------------
    # Timelines — órdenes activas representativas
    # -----------------------------------------------------------------------
    timelines = [
        # o1 — RECEIVED
        _timeline_entry(o1, None, OrderStatus.RECEIVED, recep, "Equipo ingresado: no carga post iOS"),
        # o2 — DIAGNOSING
        _timeline_entry(o2, None, OrderStatus.RECEIVED, recep, "Ingreso recepción Principal"),
        _timeline_entry(o2, OrderStatus.RECEIVED, OrderStatus.DIAGNOSING, tech1, "Asignado a diagnóstico", 1800),
        # o3 — IN_REPAIR
        _timeline_entry(o3, None, OrderStatus.RECEIVED, recep, "MacBook Air M2 — teclas intermitentes"),
        _timeline_entry(o3, OrderStatus.RECEIVED, OrderStatus.DIAGNOSING, tech1, "Diagnóstico: flex dañado", 3600),
        _timeline_entry(o3, OrderStatus.DIAGNOSING, OrderStatus.IN_REPAIR, tech1, "Iniciando limpieza flex", 900),
        # o4 — WAITING_PARTS
        _timeline_entry(o4, None, OrderStatus.RECEIVED, recep, "iPad Pro pantalla dañada"),
        _timeline_entry(o4, OrderStatus.RECEIVED, OrderStatus.DIAGNOSING, tech1, "Panel dañado confirmado", 2400),
        _timeline_entry(o4, OrderStatus.DIAGNOSING, OrderStatus.WAITING_PARTS, tech1, "Cotizando panel", 600),
        # o5 — WAITING_PARTS
        _timeline_entry(o5, None, OrderStatus.RECEIVED, recep, "HP Pavilion — olor quemado"),
        _timeline_entry(o5, OrderStatus.RECEIVED, OrderStatus.DIAGNOSING, tech2, "Daño VRM confirmado", 2700),
        _timeline_entry(o5, OrderStatus.DIAGNOSING, OrderStatus.WAITING_PARTS, tech2, "Placa cotizada", 600),
        # o6 — IN_REPAIR
        _timeline_entry(o6, None, OrderStatus.RECEIVED, recep, "PS5 lector atascado"),
        _timeline_entry(o6, OrderStatus.RECEIVED, OrderStatus.DIAGNOSING, tech2, "Diagnóstico: mecanismo roto", 5400),
        _timeline_entry(o6, OrderStatus.DIAGNOSING, OrderStatus.IN_REPAIR, tech2, "Desmontaje lector en curso", 3600),
        # o8 — RECEIVED Norte
        _timeline_entry(o8, None, OrderStatus.RECEIVED, recep2, "iPhone 15 — batería no carga Sede Norte"),
        # o9 — IN_REPAIR Norte
        _timeline_entry(o9, None, OrderStatus.RECEIVED, recep2, "Zenfone batería hinchada — URGENTE"),
        _timeline_entry(o9, OrderStatus.RECEIVED, OrderStatus.DIAGNOSING, tech3, "Batería hinchada confirmada", 900),
        _timeline_entry(o9, OrderStatus.DIAGNOSING, OrderStatus.IN_REPAIR, tech3, "Reemplazo en proceso", 1800),
        # o13 — IN_REPAIR Sur
        _timeline_entry(o13, None, OrderStatus.RECEIVED, recep, "Dell Latitude — daño por líquido"),
        _timeline_entry(o13, OrderStatus.RECEIVED, OrderStatus.DIAGNOSING, tech4, "Daño corrosión confirmado", 3600),
        _timeline_entry(o13, OrderStatus.DIAGNOSING, OrderStatus.IN_REPAIR, tech4, "Limpieza ultrasónica activa", 7200),
        # o18 — IN_REPAIR Sur
        _timeline_entry(o18, None, OrderStatus.RECEIVED, recep, "HP Pavilion SSD no detectado"),
        _timeline_entry(o18, OrderStatus.RECEIVED, OrderStatus.DIAGNOSING, tech5, "SSD muerto — reemplazo necesario", 1800),
        _timeline_entry(o18, OrderStatus.DIAGNOSING, OrderStatus.IN_REPAIR, tech5, "Instalando SSD NVMe nuevo", 2700),
        # o19 — RECEIVED sin técnico (Norte)
        _timeline_entry(o19, None, OrderStatus.RECEIVED, recep2, "Tablet S Pen — sin técnico asignado"),
    ]
    # Timelines históricas compactas
    for ho in history_orders[:10]:
        timelines.extend([
            _timeline_entry(ho, None, OrderStatus.RECEIVED, recep, "Ingreso reparación"),
            _timeline_entry(ho, OrderStatus.RECEIVED, OrderStatus.IN_REPAIR, tech1, "En reparación", 3600),
            _timeline_entry(ho, OrderStatus.IN_REPAIR, OrderStatus.COMPLETED, tech1, "Reparación completada", 1800),
        ])
    # Cancelled timelines
    _t1 = _timeline_entry(cancelled_orders[0], None, OrderStatus.RECEIVED, recep, "Ingreso Lenovo Legion")
    _t2 = _timeline_entry(cancelled_orders[0], OrderStatus.RECEIVED, OrderStatus.CANCELLED, admin, "Cliente desistió")
    timelines.extend([_t1, _t2])

    session.add_all(timelines)

    # -----------------------------------------------------------------------
    # Movimientos de inventario ligados a órdenes (used_in_repair)
    # -----------------------------------------------------------------------
    session.add_all([
        InventoryMovement(inventory_item_id=inv_tool.id,
                          movement_type=InventoryMovementType.USED_IN_REPAIR,
                          quantity_change=Decimal("-1"),
                          service_order_id=history_orders[6].id,
                          notes="Kit Torx usado en reparación Tab S9",
                          moved_by_id=tech2.id),
        InventoryMovement(inventory_item_id=inv_screen.id,
                          movement_type=InventoryMovementType.USED_IN_REPAIR,
                          quantity_change=Decimal("-1"),
                          service_order_id=history_orders[0].id,
                          notes="Pantalla iPhone reemplazada",
                          moved_by_id=tech1.id),
        InventoryMovement(inventory_item_id=inv_ssd.id,
                          movement_type=InventoryMovementType.USED_IN_REPAIR,
                          quantity_change=Decimal("-1"),
                          service_order_id=o18.id,
                          notes="SSD NVMe instalado en HP Pavilion",
                          moved_by_id=tech5.id),
        InventoryMovement(inventory_item_id=inv_low.id,
                          movement_type=InventoryMovementType.USED_IN_REPAIR,
                          quantity_change=Decimal("-1"),
                          service_order_id=o3.id,
                          notes="Alcohol para limpieza flex MacBook",
                          moved_by_id=tech1.id),
        InventoryMovement(inventory_item_id=inv_bat_apple.id,
                          movement_type=InventoryMovementType.USED_IN_REPAIR,
                          quantity_change=Decimal("-1"),
                          service_order_id=history_orders[20].id,
                          notes="Batería iPhone reemplazada",
                          moved_by_id=tech1.id),
        InventoryMovement(inventory_item_id=inv_battery.id,
                          movement_type=InventoryMovementType.USED_IN_REPAIR,
                          quantity_change=Decimal("-1"),
                          service_order_id=o9.id,
                          notes="Batería Samsung reemplazada",
                          moved_by_id=tech3.id),
        InventoryMovement(inventory_item_id=inv_pasta.id,
                          movement_type=InventoryMovementType.USED_IN_REPAIR,
                          quantity_change=Decimal("-2"),
                          service_order_id=o13.id,
                          notes="Pasta térmica aplicada tras limpieza ultrasónica",
                          moved_by_id=tech4.id),
        InventoryMovement(inventory_item_id=inv_case.id,
                          movement_type=InventoryMovementType.SALE,
                          quantity_change=Decimal("-2"),
                          service_order_id=None,
                          notes="Venta mostrador — fundas universales",
                          moved_by_id=recep.id),
        InventoryMovement(inventory_item_id=inv_screen_sam.id,
                          movement_type=InventoryMovementType.PURCHASE,
                          quantity_change=Decimal("4"),
                          service_order_id=None,
                          notes="Reposición pantallas Samsung A54",
                          moved_by_id=admin.id),
    ])

    # Ajustar stocks netos
    inv_screen.quantity_stock = Decimal("2") + Decimal("5") - Decimal("1")  # = 6
    inv_battery.quantity_stock = Decimal("12") - Decimal("1") + Decimal("3") - Decimal("1")  # = 13
    inv_ssd.quantity_stock = Decimal("8") + Decimal("10") - Decimal("1")  # = 17
    inv_low.quantity_stock = Decimal("3") - Decimal("1") - Decimal("1")  # = 1 (bajo mínimo)
    inv_tool.quantity_stock = Decimal("7") - Decimal("1")  # = 6
    inv_case.quantity_stock = Decimal("38") - Decimal("2")  # = 36
    inv_bat_apple.quantity_stock = Decimal("1") - Decimal("1")  # = 0 (bajo mínimo)
    inv_pasta.quantity_stock = Decimal("15") + Decimal("20") - Decimal("2")  # = 33

    # -----------------------------------------------------------------------
    # PDFs — distintos tipos
    # -----------------------------------------------------------------------
    session.add_all([
        PDFDocument(company_id=cid, service_order_id=history_orders[6].id,
                    document_type="delivery_receipt",
                    file_url="https://example.com/demo/pdf/entrega-historial.pdf",
                    generated_by_id=recep.id),
        PDFDocument(company_id=cid, service_order_id=None,
                    document_type="price_list",
                    file_url="https://example.com/demo/pdf/lista-precios-demo.pdf",
                    generated_by_id=admin.id),
        PDFDocument(company_id=cid, service_order_id=o3.id,
                    document_type="work_order",
                    file_url="https://example.com/demo/pdf/trabajo-ord-003.pdf",
                    generated_by_id=tech1.id),
    ])

    # -----------------------------------------------------------------------
    # RoleChangeRequest — 1 pendiente + 1 aprobada
    # -----------------------------------------------------------------------
    rcr_pending = RoleChangeRequest(
        user_id=tech3.id, company_id=cid, site_id=norte.id,
        requested_role=UserRole.ADMIN,
        requested_by_id=tech3.id, status=RoleChangeStatus.PENDING,
        reason="Solicitud de acceso admin para Sede Norte — reemplazo temporal.",
    )
    rcr_approved = RoleChangeRequest(
        user_id=recep.id, company_id=cid, site_id=principal.id,
        requested_role=UserRole.TECHNICIAN,
        requested_by_id=recep.id, approved_by_id=admin.id,
        status=RoleChangeStatus.APPROVED,
        reason="Apoyo técnico durante pico de trabajo.",
    )
    session.add_all([rcr_pending, rcr_approved])

    # -----------------------------------------------------------------------
    # TemporaryPermission — para tech1 (permiso admin_read 48h)
    # -----------------------------------------------------------------------
    session.add(TemporaryPermission(
        user_id=tech1.id, company_id=cid, site_id=principal.id,
        permission="admin_read",
        expires_at=utc_now() + timedelta(hours=48),
        granted_by_id=admin.id,
    ))

    # -----------------------------------------------------------------------
    # AuditLog — entradas para órdenes y cambios de estado
    # -----------------------------------------------------------------------
    session.add_all([
        AuditLog(actor_type="tenant", actor_id=str(recep.id),
                 company_id=cid, user_id=recep.id, site_id=principal.id,
                 action="order.create", resource_type="service_order",
                 resource_id=str(o1.id),
                 metadata_json={"order_number": o1.order_number, "status": "received"}),
        AuditLog(actor_type="tenant", actor_id=str(tech1.id),
                 company_id=cid, user_id=tech1.id, site_id=principal.id,
                 action="order.status_change", resource_type="service_order",
                 resource_id=str(o3.id),
                 metadata_json={"from": "diagnosing", "to": "in_repair"}),
        AuditLog(actor_type="tenant", actor_id=str(admin.id),
                 company_id=cid, user_id=admin.id,
                 action="role_change_request.approve", resource_type="role_change_request",
                 resource_id=str(rcr_approved.id),
                 metadata_json={"role": "technician", "site": "Principal"}),
        AuditLog(actor_type="tenant", actor_id=str(recep2.id),
                 company_id=cid, user_id=recep2.id, site_id=norte.id,
                 action="order.create", resource_type="service_order",
                 resource_id=str(o8.id),
                 metadata_json={"order_number": o8.order_number, "site": "Sede Norte"}),
    ])

    # -----------------------------------------------------------------------
    # Políticas SLA
    # -----------------------------------------------------------------------
    from app.db.models.sla_policy import SlaPolicy

    session.add_all([
        SlaPolicy(
            company_id=cid,
            name="Urgente - Taller",
            order_kind=ServiceOrderKind.WORKSHOP_INTAKE,
            priority=OrderPriority.URGENT,
            response_time_hours=1,
            resolution_time_hours=4,
            warning_threshold_hours=1,
            is_active=True,
        ),
        SlaPolicy(
            company_id=cid,
            name="Alta - Taller",
            order_kind=ServiceOrderKind.WORKSHOP_INTAKE,
            priority=OrderPriority.HIGH,
            response_time_hours=2,
            resolution_time_hours=8,
            warning_threshold_hours=2,
            is_active=True,
        ),
        SlaPolicy(
            company_id=cid,
            name="Normal - Taller",
            order_kind=ServiceOrderKind.WORKSHOP_INTAKE,
            priority=OrderPriority.MEDIUM,
            response_time_hours=4,
            resolution_time_hours=24,
            warning_threshold_hours=6,
            is_active=True,
        ),
        SlaPolicy(
            company_id=cid,
            name="Baja - Taller",
            order_kind=ServiceOrderKind.WORKSHOP_INTAKE,
            priority=OrderPriority.LOW,
            response_time_hours=8,
            resolution_time_hours=48,
            warning_threshold_hours=6,
            is_active=True,
        ),
        SlaPolicy(
            company_id=cid,
            name="Servicio en campo - Urgente",
            order_kind=ServiceOrderKind.FIELD_SERVICE,
            priority=OrderPriority.URGENT,
            response_time_hours=2,
            resolution_time_hours=8,
            warning_threshold_hours=2,
            is_active=True,
        ),
        SlaPolicy(
            company_id=cid,
            name="Global por defecto",
            response_time_hours=4,
            resolution_time_hours=24,
            warning_threshold_hours=6,
            is_active=True,
        ),
    ])

    # -----------------------------------------------------------------------
    # Contratos de servicio — 3 tipos: maintenance, warranty, field_sla
    # -----------------------------------------------------------------------
    contract_main = ServiceContract(
        company_id=cid, customer_id=c2.id,
        contract_number="DEMO-CONTRACT-001",
        name="Mantenimiento demo portal",
        contract_kind=ContractKind.MAINTENANCE,
        default_site_id=principal.id,
        allowed_order_kinds=[ServiceOrderKind.WORKSHOP_INTAKE_CONTRACT.value],
        template_json={
            "version": 1,
            "fields": [
                {"key": "location", "label": "Ubicación visita", "type": "text", "required": True},
                {"key": "urgency", "label": "Urgencia", "type": "select", "options": ["normal", "alta"]},
            ],
        },
        valid_from=date.today() - timedelta(days=30),
        valid_to=date.today() + timedelta(days=365),
        is_active=True,
    )
    contract_warranty = ServiceContract(
        company_id=cid, customer_id=c11.id,
        contract_number="DEMO-CONTRACT-002",
        name="Garantía extendida Importadora Andina",
        contract_kind=ContractKind.WARRANTY,
        default_site_id=sur.id,
        allowed_order_kinds=[
            ServiceOrderKind.WORKSHOP_INTAKE_CONTRACT.value,
            ServiceOrderKind.FIELD_SERVICE_CONTRACT.value,
        ],
        template_json={
            "version": 1,
            "fields": [
                {"key": "ticket_proveedor", "label": "Ticket proveedor", "type": "text", "required": True},
                {"key": "tipo_falla", "label": "Tipo de falla", "type": "select",
                 "options": ["hardware", "software", "físico"]},
            ],
        },
        max_orders_per_month=10,
        valid_from=date.today() - timedelta(days=90),
        valid_to=date.today() + timedelta(days=275),
        is_active=True,
    )
    contract_sla = ServiceContract(
        company_id=cid, customer_id=c7.id,
        contract_number="DEMO-CONTRACT-003",
        name="SLA Campo Tecnologías del Pacífico",
        contract_kind=ContractKind.FIELD_SLA,
        default_site_id=norte.id,
        allowed_order_kinds=[ServiceOrderKind.FIELD_SERVICE_CONTRACT.value],
        template_json={
            "version": 1,
            "fields": [
                {"key": "ciudad", "label": "Ciudad", "type": "text", "required": True},
                {"key": "nivel_sla", "label": "Nivel SLA", "type": "select",
                 "options": ["4h", "8h", "next_business_day"]},
                {"key": "contacto_sitio", "label": "Contacto en sitio", "type": "text"},
            ],
        },
        max_orders_per_month=20,
        valid_from=date.today() - timedelta(days=60),
        valid_to=date.today() + timedelta(days=305),
        is_active=True,
    )
    session.add_all([contract_main, contract_warranty, contract_sla])
    session.flush()

    # -----------------------------------------------------------------------
    # Portal: usuario y 2 órdenes visibles (tipo contrato)
    # -----------------------------------------------------------------------
    session.add(CustomerPortalUser(
        company_id=cid, customer_id=c2.id,
        email=f"portal.cliente@{DEMO_EMAIL_DOMAIN}",
        full_name="Contacto Portal Demo",
        hashed_password=pwd_hash,
        invited_by_id=admin.id,
        is_active=True,
    ))

    # Órdenes de portal (tipo contrato — visibles en portal)
    portal_order1 = _order(
        cid, next_num(), eq2, c2, OrderStatus.IN_REPAIR, OrderPriority.MEDIUM,
        tech1, "Batería reemplazada — orden portal.", "Batería defectuosa confirmada.",
        Decimal("85000"), Decimal("65000"), recep, site=principal,
        order_kind=ServiceOrderKind.WORKSHOP_INTAKE_CONTRACT,
        service_contract=contract_main, days_ago=5,
    )
    portal_order1.portal_submitted_json = {
        "location": "Carrera 15 # 90-10, Bogotá",
        "urgency": "alta",
    }
    portal_order2 = _order(
        cid, next_num(), eq2, c2, OrderStatus.COMPLETED, OrderPriority.LOW,
        tech2, "Limpieza interna semestral.", "Limpieza completada sin novedades.",
        Decimal("0"), Decimal("45000"), recep, site=principal,
        order_kind=ServiceOrderKind.WORKSHOP_INTAKE_CONTRACT,
        service_contract=contract_main, days_ago=60,
    )
    # Orden de servicio en campo vinculada al contrato SLA
    field_order = _order(
        cid, next_num(), eq9, c7, OrderStatus.RECEIVED, OrderPriority.HIGH,
        tech3, "Visita en campo — conector MagSafe doblado, equipo no carga.", None,
        Decimal("0"), Decimal("0"), recep2, site=norte,
        order_kind=ServiceOrderKind.FIELD_SERVICE_CONTRACT,
        service_contract=contract_sla, days_ago=1,
        original_owner=c7,
    )
    session.add_all([portal_order1, portal_order2, field_order])
    session.flush()
    _cost_lines(session, cid, portal_order1)
    _cost_lines(session, cid, portal_order2)
    _cost_lines(session, cid, field_order)

    # Timeline para orden de campo
    session.add(_timeline_entry(field_order, None, OrderStatus.RECEIVED, recep2,
                                 "Visita campo — SLA Tecnologías del Pacífico"))

    # Reportes de campo de ejemplo
    session.add_all([
        FieldReport(
            company_id=cid,
            site_id=norte.id,
            order_id=field_order.id,
            technician_id=tech3.id,
            title="Diagnóstico en sitio — MagSafe",
            findings="Conector MagSafe presenta doblez de 45° en pines 1 y 2. No hay corto en la placa lógica.",
            recommendations="Reemplazar conector MagSafe y cable flex asociado. Presupuesto aprobado por cliente.",
            status="submitted",
            photos_urls=[
                "https://placehold.co/600x400?text=MagSafe+doblado",
                "https://placehold.co/600x400?text=Placa+limpia",
            ],
        ),
        FieldReport(
            company_id=cid,
            site_id=norte.id,
            order_id=None,
            technician_id=tech3.id,
            title="Inspección rack de red — visita preventiva",
            findings="Switch principal con firmware desactualizado. Ventiladores en 85% de uso continuo.",
            recommendations="Programar actualización de firmware fuera de horario crítico. Revisar ventiladores en 30 días.",
            status="draft",
            photos_urls=["https://placehold.co/600x400?text=Switch+rack"],
        ),
        FieldReport(
            company_id=cid,
            site_id=principal.id,
            order_id=None,
            technician_id=tech1.id,
            title="Mantenimiento preventivo servidor",
            findings="Servidor operativo. Temperatura promedio 42°C. RAID en estado óptimo.",
            recommendations="Ninguna acción requerida. Próximo mantenimiento en 90 días.",
            status="reviewed",
            photos_urls=[],
        ),
    ])

    # Escenarios adicionales y ajuste del contador de órdenes
    apply_primary_extended_scenarios(
        session,
        company=company,
        orders=active_orders[:8],
        admin=admin,
        recep=recep,
        tech1=tech1,
        tech2=tech2,
        tech3=tech3,
        tech4=tech4,
        tech5=tech5,
        inv_battery=inv_battery,
        inv_case=inv_case,
    )

    company.next_order_number = max(company.next_order_number, num[0] + 10)
    return company
