"""
Tests for:
- ServiceOrderImage CRUD
- Order PDF generation
- Inventory analytics
"""

from decimal import Decimal

from app.core.security import SecurityUtils
from app.core.enums import UserRole
from app.db.models.customer import Customer
from app.db.models.equipment import Equipment
from app.db.models.inventory import InventoryItem
from app.db.models.rbac import Site
from app.db.models.service_order import ServiceOrder
from app.db.models.service_order_image import ServiceOrderImage
from app.db.models.user import User


def _default_site(db_session, company):
    return db_session.query(Site).filter(Site.company_id == company.id).one()


def _get_token(client, email, password="password123"):
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    ).json()["access_token"]


# ─────────────────────────────────────────────────────────────
# ServiceOrderImage CRUD
# ─────────────────────────────────────────────────────────────

def test_order_image_crud(client, db_session, seed_company_and_admin):
    company, admin = seed_company_and_admin
    site = _default_site(db_session, company)

    customer = Customer(
        company_id=company.id,
        first_name="Img",
        last_name="Test",
        email="img@test.com",
    )
    equipment = Equipment(
        company_id=company.id,
        serial_number="SN-IMG-1",
        brand="Brand",
        model="Model",
    )
    db_session.add_all([customer, equipment])
    db_session.commit()
    db_session.refresh(customer)
    db_session.refresh(equipment)

    order = ServiceOrder(
        company_id=company.id,
        site_id=site.id,
        order_number="MAIN-IT-IMG-1",
        equipment_id=equipment.id,
        current_customer_id=customer.id,
        problem_description="Problem",
        status="received",
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    token = _get_token(client, "admin@test.com")
    headers = {"Authorization": f"Bearer {token}"}
    order_id = str(order.id)

    # List empty
    r = client.get(f"/api/v1/orders/{order_id}/images", headers=headers)
    assert r.status_code == 200
    assert r.json() == []

    # Create two images
    r1 = client.post(
        f"/api/v1/orders/{order_id}/images",
        headers=headers,
        json={
            "url": "https://example.com/img1.jpg",
            "caption": "Foto del daño",
            "sort_order": 1,
        },
    )
    assert r1.status_code == 201
    img1 = r1.json()
    assert img1["url"] == "https://example.com/img1.jpg"
    assert img1["caption"] == "Foto del daño"
    assert img1["sort_order"] == 1
    img1_id = img1["id"]

    r2 = client.post(
        f"/api/v1/orders/{order_id}/images",
        headers=headers,
        json={
            "url": "https://example.com/img2.jpg",
            "caption": "Foto posterior",
            "sort_order": 2,
        },
    )
    assert r2.status_code == 201
    img2_id = r2.json()["id"]

    # List returns both ordered by sort_order
    r = client.get(f"/api/v1/orders/{order_id}/images", headers=headers)
    assert r.status_code == 200
    images = r.json()
    assert len(images) == 2
    assert images[0]["id"] == img1_id
    assert images[1]["id"] == img2_id

    # Delete first image
    d = client.delete(
        f"/api/v1/orders/{order_id}/images/{img1_id}",
        headers=headers,
    )
    assert d.status_code == 204

    # List now has one
    r = client.get(f"/api/v1/orders/{order_id}/images", headers=headers)
    assert len(r.json()) == 1

    # Delete same image again -> 404
    d2 = client.delete(
        f"/api/v1/orders/{order_id}/images/{img1_id}",
        headers=headers,
    )
    assert d2.status_code == 404

    # Image on non-existent order -> 404
    bad = client.post(
        "/api/v1/orders/00000000-0000-0000-0000-000000000000/images",
        headers=headers,
        json={"url": "x", "sort_order": 1},
    )
    assert bad.status_code == 404


# ─────────────────────────────────────────────────────────────
# Order PDF generation
# ─────────────────────────────────────────────────────────────

def test_order_pdf_generation(client, db_session, seed_company_and_admin):
    company, admin = seed_company_and_admin
    site = _default_site(db_session, company)

    customer = Customer(
        company_id=company.id,
        first_name="PDF",
        last_name="Customer",
        email="pdf@test.com",
        phone="3001234567",
    )
    equipment = Equipment(
        company_id=company.id,
        serial_number="SN-PDF-1",
        brand="TestBrand",
        model="TestModel",
        equipment_type="Laptop",
    )
    db_session.add_all([customer, equipment])
    db_session.commit()
    db_session.refresh(customer)
    db_session.refresh(equipment)

    order = ServiceOrder(
        company_id=company.id,
        site_id=site.id,
        order_number="MAIN-IT-PDF-1",
        equipment_id=equipment.id,
        current_customer_id=customer.id,
        problem_description="Pantalla rota",
        diagnosis_notes="Cambio de display",
        status="diagnosing",
        priority="high",
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    token = _get_token(client, "admin@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get(f"/api/v1/orders/{order.id}/print", headers=headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert 'inline; filename="orden-MAIN-IT-PDF-1.pdf"' in r.headers["content-disposition"]
    # Verify it starts with PDF magic bytes
    assert r.content.startswith(b"%PDF-1.")

    # Non-existent order
    bad = client.get(
        "/api/v1/orders/00000000-0000-0000-0000-000000000000/print",
        headers=headers,
    )
    assert bad.status_code == 404


# ─────────────────────────────────────────────────────────────
# Inventory analytics
# ─────────────────────────────────────────────────────────────

def test_inventory_analytics_empty_company(client, seed_company_and_admin):
    token = _get_token(client, "admin@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get("/api/v1/inventory/analytics", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total_items"] == 0
    assert data["low_stock_count"] == 0
    assert data["total_value"] == 0.0
    assert data["movements_this_month"] == 0
    assert all(v == 0 for v in data["movement_breakdown"].values())


def test_inventory_analytics_with_items(client, db_session, seed_company_and_admin):
    company, _admin = seed_company_and_admin

    # Create items with various stock levels
    item_ok = InventoryItem(
        company_id=company.id,
        sku="SKU-OK",
        name="Item OK",
        quantity_stock=Decimal("10"),
        quantity_minimum=Decimal("5"),
        unit_cost=Decimal("100"),
        unit_price=Decimal("150"),
    )
    item_low = InventoryItem(
        company_id=company.id,
        sku="SKU-LOW",
        name="Item Low",
        quantity_stock=Decimal("2"),
        quantity_minimum=Decimal("5"),
        unit_cost=Decimal("50"),
        unit_price=Decimal("80"),
    )
    item_zero = InventoryItem(
        company_id=company.id,
        sku="SKU-ZERO",
        name="Item Zero",
        quantity_stock=Decimal("0"),
        quantity_minimum=Decimal("3"),
        unit_cost=Decimal("200"),
        unit_price=Decimal("300"),
    )
    db_session.add_all([item_ok, item_low, item_zero])
    db_session.commit()

    token = _get_token(client, "admin@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get("/api/v1/inventory/analytics", headers=headers)
    assert r.status_code == 200
    data = r.json()

    assert data["total_items"] == 3
    assert data["low_stock_count"] == 2  # low + zero
    # total_value = 10*100 + 2*50 + 0*200 = 1100
    assert data["total_value"] == 1100.0
    assert data["movements_this_month"] == 0
    assert all(v == 0 for v in data["movement_breakdown"].values())
