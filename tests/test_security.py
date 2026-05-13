"""Aislamiento entre empresas y panel de plataforma."""

from uuid import uuid4

from app.core.enums import PlatformRole, UserRole
from app.core.security import SecurityUtils
from app.db.models.audit_log import AuditLog
from app.db.models.company import Company
from app.db.models.customer import Customer
from app.db.models.equipment import Equipment
from app.db.models.platform_user import PlatformUser
from app.db.models.service_order import ServiceOrder
from app.db.models.user import User


def test_order_idor_other_company(client, db_session):
    company_a = Company(name="A", nit_rut="111", address="x")
    company_b = Company(name="B", nit_rut="222", address="y")
    db_session.add_all([company_a, company_b])
    db_session.commit()
    db_session.refresh(company_a)
    db_session.refresh(company_b)

    admin_a = User(
        company_id=company_a.id,
        email="a@a.com",
        full_name="Admin A",
        hashed_password=SecurityUtils.hash_password("pw"),
        role=UserRole.ADMIN,
    )
    admin_b = User(
        company_id=company_b.id,
        email="b@b.com",
        full_name="Admin B",
        hashed_password=SecurityUtils.hash_password("pw"),
        role=UserRole.ADMIN,
    )
    db_session.add_all([admin_a, admin_b])
    cust = Customer(company_id=company_a.id, first_name="c", last_name="c", email="c@c.com")
    eq = Equipment(company_id=company_a.id, serial_number="s1", brand="b", model="m")
    db_session.add_all([cust, eq])
    db_session.commit()
    db_session.refresh(cust)
    db_session.refresh(eq)

    order = ServiceOrder(
        id=uuid4(),
        company_id=company_a.id,
        order_number="ORD-1",
        equipment_id=eq.id,
        current_customer_id=cust.id,
        problem_description="x",
    )
    db_session.add(order)
    db_session.commit()

    token_b = client.post(
        "/api/v1/auth/login",
        json={"email": "b@b.com", "password": "pw"},
    ).json()["access_token"]

    res = client.get(
        f"/api/v1/orders/{order.id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res.status_code == 404


def test_platform_route_rejects_tenant_token(client, db_session, seed_company_and_admin):
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "password123"},
    ).json()["access_token"]
    res = client.get(
        "/api/platform/v1/companies/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 401


def test_impersonate_creates_audit_and_tokens(client, db_session):
    company = Company(name="C", nit_rut="333", address="z")
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)

    super_u = PlatformUser(
        email="super@example.com",
        full_name="Super",
        hashed_password=SecurityUtils.hash_password("superpw12"),
        role=PlatformRole.SUPER_ADMIN,
    )
    db_session.add(super_u)
    db_session.commit()
    db_session.refresh(super_u)

    login = client.post(
        "/api/platform/v1/auth/login",
        json={"email": "super@example.com", "password": "superpw12"},
    )
    assert login.status_code == 200
    plat_token = login.json()["access_token"]

    res = client.post(
        "/api/platform/v1/impersonate",
        headers={"Authorization": f"Bearer {plat_token}"},
        json={"company_id": str(company.id)},
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data and "refresh_token" in data

    payload = SecurityUtils.decode_token(data["access_token"])
    assert payload is not None
    assert payload.get("act_as_company_id") == str(company.id)

    db_session.expire_all()
    row = db_session.query(AuditLog).filter(AuditLog.action == "platform.impersonate").first()
    assert row is not None
    assert str(row.company_id) == str(company.id)
