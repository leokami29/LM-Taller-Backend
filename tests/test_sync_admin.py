from contextlib import contextmanager
from datetime import timedelta
from uuid import uuid4

from app.core.dt import utc_now
from app.core.enums import OrderPriority, OrderStatus, SubscriptionStatus
from app.core.security import SecurityUtils
from app.db.models.customer import Customer
from app.db.models.equipment import Equipment
from app.db.models.rbac import Site
from app.db.models.service_order import ServiceOrder
from app.services.sync_admin import context as sync_context_module


def _auth_headers(user):
    token = SecurityUtils.create_tenant_access_token(user.id, user.company_id)
    return {"Authorization": f"Bearer {token}"}


def _patch_tenant_session(monkeypatch, db_session, calls):
    @contextmanager
    def fake_tenant_session_for_company(company_id):
        calls.append(company_id)
        yield db_session

    monkeypatch.setattr(sync_context_module, "tenant_session_for_company", fake_tenant_session_for_company)


def test_sync_admin_bootstrap_uses_tenant_session_for_company(
    client,
    db_session,
    seed_company_and_admin,
    monkeypatch,
):
    company, admin = seed_company_and_admin
    calls = []
    _patch_tenant_session(monkeypatch, db_session, calls)

    response = client.get("/api/v1/sync/admin/bootstrap", headers=_auth_headers(admin))

    assert response.status_code == 200
    body = response.json()
    assert body["company_id"] == str(company.id)
    assert body["company"]["id"] == str(company.id)
    assert len(body["users"]) == 1
    assert calls == [company.id]


def test_sync_admin_push_site_create_is_idempotent(
    client,
    db_session,
    seed_company_and_admin,
    monkeypatch,
):
    company, admin = seed_company_and_admin
    calls = []
    _patch_tenant_session(monkeypatch, db_session, calls)
    site_id = uuid4()
    mutation = {
        "mutation_id": str(uuid4()),
        "entity": "site",
        "entity_id": str(site_id),
        "op": "create",
        "updated_at": utc_now().isoformat(),
        "payload": {"name": "Sucursal Norte", "location": "Zona norte"},
    }

    first = client.post(
        "/api/v1/sync/admin/push",
        headers=_auth_headers(admin),
        json={"mutations": [mutation]},
    )
    second = client.post(
        "/api/v1/sync/admin/push",
        headers=_auth_headers(admin),
        json={"mutations": [mutation]},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["results"][0]["status"] == "applied"
    assert second.json()["results"][0]["status"] == "applied"
    site = db_session.query(Site).filter(Site.id == site_id, Site.company_id == company.id).first()
    assert site is not None
    assert site.name == "Sucursal Norte"
    assert calls == [company.id, company.id]


def test_sync_admin_push_rejects_expired_active_subscription_payload(
    client,
    db_session,
    seed_company_and_admin,
    monkeypatch,
):
    company, admin = seed_company_and_admin
    calls = []
    _patch_tenant_session(monkeypatch, db_session, calls)
    mutation = {
        "mutation_id": str(uuid4()),
        "entity": "company",
        "entity_id": str(company.id),
        "op": "update",
        "updated_at": utc_now().isoformat(),
        "payload": {
            "subscription_status": SubscriptionStatus.ACTIVE.value,
            "current_period_end": (utc_now() - timedelta(days=1)).isoformat(),
        },
    }

    response = client.post(
        "/api/v1/sync/admin/push",
        headers=_auth_headers(admin),
        json={"mutations": [mutation]},
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["status"] == "rejected"
    assert "anterior" in result["detail"].lower()


def test_sync_admin_push_customer_create(
    client,
    db_session,
    seed_company_and_admin,
    monkeypatch,
):
    company, admin = seed_company_and_admin
    calls = []
    _patch_tenant_session(monkeypatch, db_session, calls)
    customer_id = uuid4()
    mutation = {
        "mutation_id": str(uuid4()),
        "entity": "customer",
        "entity_id": str(customer_id),
        "op": "create",
        "updated_at": utc_now().isoformat(),
        "payload": {
            "first_name": "Ana",
            "last_name": "García",
            "email": "ana@example.com",
            "phone": "+56912345678",
        },
    }

    response = client.post(
        "/api/v1/sync/admin/push",
        headers=_auth_headers(admin),
        json={"mutations": [mutation]},
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "applied"
    customer = (
        db_session.query(Customer)
        .filter(Customer.id == customer_id, Customer.company_id == company.id)
        .first()
    )
    assert customer is not None
    assert customer.first_name == "Ana"
    assert customer.last_name == "García"


def test_sync_admin_push_service_order_create(
    client,
    db_session,
    seed_company_and_admin,
    monkeypatch,
):
    company, admin = seed_company_and_admin
    calls = []
    _patch_tenant_session(monkeypatch, db_session, calls)
    customer = Customer(
        company_id=company.id,
        first_name="Pedro",
        last_name="Ruiz",
        email="pedro@example.com",
    )
    equipment = Equipment(
        company_id=company.id,
        serial_number="SN-OFF-001",
        brand="Samsung",
        model="A54",
    )
    db_session.add(customer)
    db_session.add(equipment)
    db_session.commit()
    db_session.refresh(customer)
    db_session.refresh(equipment)
    order_id = uuid4()
    mutation = {
        "mutation_id": str(uuid4()),
        "entity": "service_order",
        "entity_id": str(order_id),
        "op": "create",
        "updated_at": utc_now().isoformat(),
        "payload": {
            "order_number": "OS-OFF-001",
            "order_kind": "workshop_intake",
            "equipment_id": str(equipment.id),
            "current_customer_id": str(customer.id),
            "status": OrderStatus.RECEIVED.value,
            "priority": OrderPriority.MEDIUM.value,
            "problem_description": "Pantalla rota",
        },
    }

    response = client.post(
        "/api/v1/sync/admin/push",
        headers=_auth_headers(admin),
        json={"mutations": [mutation]},
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "applied"
    order = (
        db_session.query(ServiceOrder)
        .filter(ServiceOrder.id == order_id, ServiceOrder.company_id == company.id)
        .first()
    )
    assert order is not None
    assert order.order_number == "OS-OFF-001"
    assert order.problem_description == "Pantalla rota"
