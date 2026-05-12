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
