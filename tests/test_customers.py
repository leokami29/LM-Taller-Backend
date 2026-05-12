from app.core.enums import UserRole
from app.core.security import SecurityUtils
from app.db.models.company import Company
from app.db.models.user import User


def test_customer_tenant_isolation(client, db_session, seed_company_and_admin):
    _company_a, _admin_a = seed_company_and_admin
    company_b = Company(name="Otra", nit_rut="800000002", address="Calle 2")
    db_session.add(company_b)
    db_session.commit()
    db_session.refresh(company_b)
    admin_b = User(
        company_id=company_b.id,
        email="b@test.com",
        full_name="B",
        hashed_password=SecurityUtils.hash_password("password123"),
        role=UserRole.ADMIN,
    )
    db_session.add(admin_b)
    db_session.commit()

    login_a = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "password123"},
    ).json()["access_token"]
    login_b = client.post(
        "/api/v1/auth/login",
        json={"email": "b@test.com", "password": "password123"},
    ).json()["access_token"]

    c = client.post(
        "/api/v1/customers/",
        headers={"Authorization": f"Bearer {login_a}"},
        json={
            "first_name": "Juan",
            "last_name": "Pérez",
            "email": "juan@cliente.com",
        },
    )
    assert c.status_code == 201
    customer_id = c.json()["id"]

    other = client.get(
        f"/api/v1/customers/{customer_id}",
        headers={"Authorization": f"Bearer {login_b}"},
    )
    assert other.status_code == 404
