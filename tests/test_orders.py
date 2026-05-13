from app.core.enums import UserRole
from app.core.security import SecurityUtils
from app.db.models.customer import Customer
from app.db.models.equipment import Equipment
from app.db.models.user import User


def test_order_invalid_status_transition(client, db_session, seed_company_and_admin):
    company, admin = seed_company_and_admin
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
        },
    )
    assert order_res.status_code == 201
    order_id = order_res.json()["id"]

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
        },
    )
    assert order_res.status_code == 201
    order_id = order_res.json()["id"]
    assert order_res.json()["total_cost"] == "0.00"

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
