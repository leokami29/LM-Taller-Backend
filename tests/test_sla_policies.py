from app.core.enums import OrderPriority, ServiceOrderKind, UserRole
from app.core.security import SecurityUtils
from app.db.models.user import User
from app.services.sla_policy_service import (
    compute_estimated_completion,
    find_matching_sla_policy,
)
from app.services.order_service import create_service_order


def _login(client, email="admin@test.com", password="password123"):
    res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200
    return res.json()["access_token"]


def test_create_and_list_sla_policies(client, seed_company_and_admin):
    company, _admin = seed_company_and_admin
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    create_res = client.post(
        "/api/v1/sla-policies/",
        headers=headers,
        json={
            "name": "Política demo",
            "order_kind": "workshop_intake",
            "priority": "high",
            "response_time_hours": 2,
            "resolution_time_hours": 8,
            "warning_threshold_hours": 2,
        },
    )
    assert create_res.status_code == 201
    data = create_res.json()
    assert data["name"] == "Política demo"
    assert data["order_kind"] == "workshop_intake"
    assert data["priority"] == "high"
    assert data["resolution_time_hours"] == 8

    list_res = client.get("/api/v1/sla-policies/", headers=headers)
    assert list_res.status_code == 200
    payload = list_res.json()
    assert payload["total"] == 1


def test_update_and_delete_sla_policy(client, seed_company_and_admin):
    company, _admin = seed_company_and_admin
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    create_res = client.post(
        "/api/v1/sla-policies/",
        headers=headers,
        json={"name": "Original", "resolution_time_hours": 24},
    )
    policy_id = create_res.json()["id"]

    update_res = client.put(
        f"/api/v1/sla-policies/{policy_id}",
        headers=headers,
        json={"name": "Actualizada", "resolution_time_hours": 12},
    )
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "Actualizada"
    assert update_res.json()["resolution_time_hours"] == 12

    del_res = client.delete(f"/api/v1/sla-policies/{policy_id}", headers=headers)
    assert del_res.status_code == 204

    get_res = client.get(f"/api/v1/sla-policies/{policy_id}", headers=headers)
    assert get_res.status_code == 404


def test_sla_policy_matching_and_order_completion(client, db_session, seed_company_and_admin):
    company, admin = seed_company_and_admin
    from app.db.models.customer import Customer
    from app.db.models.equipment import Equipment
    from app.db.models.rbac import Site
    from app.db.models.sla_policy import SlaPolicy

    site = db_session.query(Site).filter(Site.company_id == company.id).one()
    customer = Customer(company_id=company.id, first_name="SLA", last_name="Test", email="sla@test.com")
    equipment = Equipment(company_id=company.id, serial_number="SLA-001", brand="X", model="Y")
    db_session.add(customer)
    db_session.add(equipment)

    policy = SlaPolicy(
        company_id=company.id,
        name="Match",
        order_kind=ServiceOrderKind.WORKSHOP_INTAKE,
        priority=OrderPriority.HIGH,
        response_time_hours=1,
        resolution_time_hours=8,
        warning_threshold_hours=2,
    )
    db_session.add(policy)
    db_session.commit()
    db_session.refresh(customer)
    db_session.refresh(equipment)

    matched = find_matching_sla_policy(
        db_session,
        company_id=company.id,
        order_kind=ServiceOrderKind.WORKSHOP_INTAKE,
        priority=OrderPriority.HIGH,
    )
    assert matched is not None
    assert matched.id == policy.id

    from datetime import datetime, timezone, timedelta
    start = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    completion = compute_estimated_completion(
        db_session,
        company_id=company.id,
        order_kind=ServiceOrderKind.WORKSHOP_INTAKE,
        priority=OrderPriority.HIGH,
        start_at=start,
    )
    assert completion is not None
    assert completion == start + timedelta(hours=8)

    order = create_service_order(
        db_session,
        company_id=company.id,
        equipment_id=equipment.id,
        current_customer_id=customer.id,
        original_owner_id=customer.id,
        problem_description="Falla SLA",
        priority=OrderPriority.HIGH,
        created_by_id=admin.id,
        order_kind=ServiceOrderKind.WORKSHOP_INTAKE,
        site_id=site.id,
    )
    db_session.commit()
    assert order.estimated_completion is not None


def test_sla_policy_admin_permission(client, db_session, seed_company_and_admin):
    company, _admin = seed_company_and_admin
    viewer = User(
        company_id=company.id,
        email="viewer@test.com",
        full_name="Viewer",
        hashed_password=SecurityUtils.hash_password("password123"),
        role=UserRole.VIEWER,
    )
    db_session.add(viewer)
    db_session.commit()

    viewer_token = _login(client, email="viewer@test.com")
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

    create_res = client.post(
        "/api/v1/sla-policies/",
        headers=viewer_headers,
        json={"name": "No permitida"},
    )
    assert create_res.status_code == 403
