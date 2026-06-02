"""API pública de seguimiento y URLs de QR."""

from app.db.models.customer import Customer
from app.db.models.equipment import Equipment
from app.db.models.rbac import Site
from app.db.models.service_order import ServiceOrder
from app.services.tracking_urls import build_public_tracking_url


def _seed_order(db_session, company, *, tracking_code="TG-261001", settings_json=None):
    site = db_session.query(Site).filter(Site.company_id == company.id).one()
    if settings_json is not None:
        company.settings_json = settings_json
        db_session.commit()
    customer = Customer(
        company_id=company.id,
        first_name="Pub",
        last_name="Lic",
        email="pub@test.com",
    )
    equipment = Equipment(
        company_id=company.id,
        serial_number="SN-PUB-9999",
        brand="Marca",
        model="Modelo",
        equipment_type="Laptop",
    )
    db_session.add_all([customer, equipment])
    db_session.commit()
    order = ServiceOrder(
        company_id=company.id,
        site_id=site.id,
        order_number="PUB-001",
        tracking_code=tracking_code,
        equipment_id=equipment.id,
        current_customer_id=customer.id,
        problem_description="Pantalla rota en esquina superior",
        status="received",
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_build_public_tracking_url():
    url = build_public_tracking_url(
        tenant_slug="taller-central",
        tracking_code="tg-261001",
    )
    assert "/es/seguimiento/taller-central/TG-261001" in url
    assert url.startswith("http")


def test_public_tracking_found(client, db_session, seed_company_and_admin):
    company, _ = seed_company_and_admin
    _seed_order(db_session, company)

    r = client.get("/api/v1/public/seguimiento/default/TG-261001")
    assert r.status_code == 200
    body = r.json()
    assert body["tracking_code"] == "TG-261001"
    assert body["order_number"] == "PUB-001"
    assert "diagnosis" not in body
    assert "total_cost" not in body
    assert body["serial_masked"].endswith("9999")
    assert len(body["problem_summary"]) <= 120


def test_public_tracking_not_found(client):
    r = client.get("/api/v1/public/seguimiento/default/TG-000000")
    assert r.status_code == 404
    assert "No encontramos" in r.json()["detail"]


def test_public_tracking_disabled(client, db_session, seed_company_and_admin):
    company, _ = seed_company_and_admin
    _seed_order(
        db_session,
        company,
        tracking_code="TG-261002",
        settings_json={"public_tracking_enabled": False},
    )

    r = client.get("/api/v1/public/seguimiento/default/TG-261002")
    assert r.status_code == 403
