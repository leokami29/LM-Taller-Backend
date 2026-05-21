from datetime import datetime, timedelta, timezone

from app.core.enums import ServiceOrderKind, UserRole
from app.core.order_number import parse_order_number
from app.core.security import SecurityUtils
from app.db.models.customer import Customer
from app.db.models.equipment import Equipment
from app.db.models.rbac import Site
from app.db.models.service_contract import ServiceContract
from app.db.models.user import User


def _default_site(db_session, company):
    return db_session.query(Site).filter(Site.company_id == company.id).one()


def test_order_invalid_status_transition(client, db_session, seed_company_and_admin):
    company, admin = seed_company_and_admin
    site = _default_site(db_session, company)
    tech = User(
        company_id=company.id,
        email="tech2@test.com",
        full_name="Tech2",
        hashed_password=SecurityUtils.hash_password("password123"),
        role=UserRole.TECHNICIAN,
    )
    db_session.add(tech)
    customer = Customer(
        company_id=company.id,
        first_name="Ana",
        last_name="López",
        email="ana@mail.com",
    )
    equipment = Equipment(
        company_id=company.id,
        serial_number="SN-999",
        brand="X",
        model="Y",
    )
    db_session.add(customer)
    db_session.add(equipment)
    db_session.commit()
    db_session.refresh(customer)
    db_session.refresh(equipment)

    admin_token = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "password123"},
    ).json()["access_token"]

    order_res = client.post(
        "/api/v1/orders/",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "equipment_id": str(equipment.id),
            "current_customer_id": str(customer.id),
            "problem_description": "No enciende",
            "site_id": str(site.id),
        },
    )
    assert order_res.status_code == 201
    order_id = order_res.json()["id"]
    assert order_res.json()["order_number"].startswith("MAIN-IT-")

    tech_token = client.post(
        "/api/v1/auth/login",
        json={"email": "tech2@test.com", "password": "password123"},
    ).json()["access_token"]

    bad = client.patch(
        f"/api/v1/orders/{order_id}/status",
        headers={"Authorization": f"Bearer {tech_token}"},
        json={"status": "completed"},
    )
    assert bad.status_code == 400

    ok = client.patch(
        f"/api/v1/orders/{order_id}/status",
        headers={"Authorization": f"Bearer {tech_token}"},
        json={"status": "diagnosing"},
    )
    assert ok.status_code == 200


def test_order_cost_lines_crud_and_totals(client, db_session, seed_company_and_admin):
    company, admin = seed_company_and_admin
    site = _default_site(db_session, company)
    customer = Customer(
        company_id=company.id,
        first_name="Luis",
        last_name="Cost",
        email="luis.cost@test.com",
    )
    equipment = Equipment(
        company_id=company.id,
        serial_number="SN-COST-1",
        brand="Z",
        model="Q",
    )
    db_session.add(customer)
    db_session.add(equipment)
    db_session.commit()
    db_session.refresh(customer)
    db_session.refresh(equipment)

    admin_token = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "password123"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    order_res = client.post(
        "/api/v1/orders/",
        headers=headers,
        json={
            "equipment_id": str(equipment.id),
            "current_customer_id": str(customer.id),
            "problem_description": "Prueba líneas de costo",
            "site_id": str(site.id),
        },
    )
    assert order_res.status_code == 201
    order_id = order_res.json()["id"]
    assert order_res.json()["total_cost"] == "0.00"
    assert "MAIN-IT-" in order_res.json()["order_number"]

    r1 = client.post(
        f"/api/v1/orders/{order_id}/cost-lines",
        headers=headers,
        json={"category": "labor", "amount": "80.00", "description": "Diagnóstico"},
    )
    assert r1.status_code == 201
    r2 = client.post(
        f"/api/v1/orders/{order_id}/cost-lines",
        headers=headers,
        json={"category": "parts", "amount": "45.50", "description": "Cable USB-C"},
    )
    assert r2.status_code == 201

    order_get = client.get(f"/api/v1/orders/{order_id}", headers=headers)
    assert order_get.status_code == 200
    body = order_get.json()
    assert body["cost_labor"] == "80.00"
    assert body["cost_parts"] == "45.50"
    assert body["total_cost"] == "125.50"

    lines = client.get(f"/api/v1/orders/{order_id}/cost-lines", headers=headers)
    assert lines.status_code == 200
    assert len(lines.json()) == 2

    line_id = r1.json()["id"]
    up = client.put(
        f"/api/v1/orders/{order_id}/cost-lines/{line_id}",
        headers=headers,
        json={"amount": "100.00"},
    )
    assert up.status_code == 200
    order_get2 = client.get(f"/api/v1/orders/{order_id}", headers=headers).json()
    assert order_get2["cost_labor"] == "100.00"
    assert order_get2["total_cost"] == "145.50"

    bad = client.put(
        f"/api/v1/orders/{order_id}",
        headers=headers,
        json={"cost_parts": "1.00", "cost_labor": "2.00"},
    )
    assert bad.status_code == 400

    de = client.delete(
        f"/api/v1/orders/{order_id}/cost-lines/{line_id}",
        headers=headers,
    )
    assert de.status_code == 204
    order_get3 = client.get(f"/api/v1/orders/{order_id}", headers=headers).json()
    assert order_get3["cost_labor"] == "0.00"
    assert order_get3["cost_parts"] == "45.50"
    assert order_get3["total_cost"] == "45.50"


def test_order_intake_fields(client, db_session, seed_company_and_admin):
    company, admin = seed_company_and_admin
    site = Site(
        company_id=company.id,
        code="CENTRAL",
        name="Sede Central",
        location="Bogotá",
        is_active=True,
    )
    tech = User(
        company_id=company.id,
        email="tech.intake@test.com",
        full_name="Técnico Intake",
        hashed_password=SecurityUtils.hash_password("password123"),
        role=UserRole.TECHNICIAN,
    )
    customer = Customer(
        company_id=company.id,
        first_name="Pedro",
        last_name="Intake",
        email="pedro.intake@test.com",
    )
    equipment = Equipment(
        company_id=company.id,
        serial_number="SN-INTAKE-1",
        brand="Samsung",
        model="A54",
    )
    db_session.add(site)
    db_session.add(tech)
    db_session.add(customer)
    db_session.add(equipment)
    db_session.commit()
    db_session.refresh(site)
    db_session.refresh(tech)
    db_session.refresh(customer)
    db_session.refresh(equipment)

    admin_token = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "password123"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    received_at = datetime(2026, 5, 18, 11, 26, 30, tzinfo=timezone.utc)
    promised = received_at + timedelta(days=2)

    res = client.post(
        "/api/v1/orders/",
        headers=headers,
        json={
            "equipment_id": str(equipment.id),
            "current_customer_id": str(customer.id),
            "problem_description": "Pantalla rota al caer",
            "site_id": str(site.id),
            "received_at": received_at.isoformat(),
            "received_by_id": str(admin.id),
            "customer_po_number": "PO-CLIENT-99",
            "sales_area": "AREA VENTA",
            "assigned_to_id": str(tech.id),
            "estimated_completion": promised.isoformat(),
            "device_condition_on_entry": "Golpe esquina superior",
            "priority": "high",
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["site_id"] == str(site.id)
    assert body["customer_po_number"] == "PO-CLIENT-99"
    assert body["sales_area"] == "AREA VENTA"
    assert body["assigned_to_id"] == str(tech.id)
    assert body["device_condition_on_entry"] == "Golpe esquina superior"
    assert body["priority"] == "high"
    assert "Pantalla rota" in body["problem_description"]
    assert "[Condición al ingreso" not in body["problem_description"]

    bad = client.post(
        "/api/v1/orders/",
        headers=headers,
        json={
            "equipment_id": str(equipment.id),
            "current_customer_id": str(customer.id),
            "problem_description": "Otra orden",
            "site_id": str(site.id),
            "received_at": received_at.isoformat(),
            "estimated_completion": (received_at - timedelta(hours=1)).isoformat(),
        },
    )
    assert bad.status_code == 400


def test_order_numbering_sequences_by_site_and_kind(client, db_session, seed_company_and_admin):
    company, admin = seed_company_and_admin
    site_a = Site(company_id=company.id, code="BOG", name="Bogotá", is_active=True)
    site_b = Site(company_id=company.id, code="MED", name="Medellín", is_active=True)
    customer = Customer(
        company_id=company.id,
        first_name="Seq",
        last_name="Test",
        email="seq@test.com",
    )
    equipment = Equipment(
        company_id=company.id,
        serial_number="SN-SEQ-1",
        brand="A",
        model="B",
    )
    db_session.add_all([site_a, site_b, customer, equipment])
    db_session.commit()
    db_session.refresh(site_a)
    db_session.refresh(site_b)
    db_session.refresh(customer)
    db_session.refresh(equipment)

    token = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "password123"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    base = {
        "equipment_id": str(equipment.id),
        "current_customer_id": str(customer.id),
        "problem_description": "Orden de prueba secuencia",
    }

    r1 = client.post(
        "/api/v1/orders/",
        headers=headers,
        json={**base, "site_id": str(site_a.id), "order_kind": "workshop_intake"},
    )
    r2 = client.post(
        "/api/v1/orders/",
        headers=headers,
        json={**base, "site_id": str(site_a.id), "order_kind": "workshop_intake"},
    )
    r3 = client.post(
        "/api/v1/orders/",
        headers=headers,
        json={**base, "site_id": str(site_a.id), "order_kind": "workshop_intake_contract"},
    )
    r4 = client.post(
        "/api/v1/orders/",
        headers=headers,
        json={**base, "site_id": str(site_b.id), "order_kind": "workshop_intake"},
    )
    assert r1.status_code == 201, r1.text
    assert r2.status_code == 201, r2.text
    assert r3.status_code == 400
    assert r4.status_code == 201, r4.text

    n1 = r1.json()["order_number"]
    n2 = r2.json()["order_number"]
    n4 = r4.json()["order_number"]
    p1 = parse_order_number(n1)
    p2 = parse_order_number(n2)
    p4 = parse_order_number(n4)
    assert p1 and p2 and p4
    assert p1.site_code == "BOG" and p1.kind_prefix == "IT" and p1.sequence == 1
    assert p2.sequence == 2
    assert n4.startswith("MED-IT-")
    assert p4.sequence == 1

    preview = client.get(
        "/api/v1/orders/next-number",
        headers=headers,
        params={"site_id": str(site_a.id), "order_kind": "workshop_intake"},
    )
    assert preview.status_code == 200
    preview_parsed = parse_order_number(preview.json()["order_number"])
    assert preview_parsed is not None
    assert preview_parsed.sequence == 3
    assert preview_parsed.kind_prefix == "IT"


def test_contract_order_requires_contract(client, db_session, seed_company_and_admin):
    company, _admin = seed_company_and_admin
    site = _default_site(db_session, company)
    customer = Customer(
        company_id=company.id,
        first_name="Contr",
        last_name="Acto",
        email="contr@test.com",
    )
    equipment = Equipment(
        company_id=company.id,
        serial_number="SN-CON-1",
        brand="X",
        model="Y",
    )
    db_session.add_all([customer, equipment])
    db_session.commit()
    db_session.refresh(customer)
    db_session.refresh(equipment)

    token = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "password123"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    missing = client.post(
        "/api/v1/orders/",
        headers=headers,
        json={
            "equipment_id": str(equipment.id),
            "current_customer_id": str(customer.id),
            "problem_description": "Orden contrato sin id",
            "site_id": str(site.id),
            "order_kind": "workshop_intake_contract",
        },
    )
    assert missing.status_code == 400

    site = _default_site(db_session, company)
    contract = ServiceContract(
        company_id=company.id,
        customer_id=customer.id,
        contract_number="POL-001",
        name="Póliza demo",
        default_site_id=site.id,
        allowed_order_kinds=["workshop_intake_contract"],
        is_active=True,
    )
    db_session.add(contract)
    db_session.commit()
    db_session.refresh(contract)

    ok = client.post(
        "/api/v1/orders/",
        headers=headers,
        json={
            "equipment_id": str(equipment.id),
            "current_customer_id": str(customer.id),
            "problem_description": "Orden con contrato válido",
            "site_id": str(site.id),
            "order_kind": "workshop_intake_contract",
            "service_contract_id": str(contract.id),
        },
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["order_number"].startswith("MAIN-ITC-")
    assert ok.json()["order_kind"] == "workshop_intake_contract"
