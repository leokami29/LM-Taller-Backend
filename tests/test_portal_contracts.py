from app.core.enums import PlanTier, ServiceOrderKind, UserRole
from app.core.security import SecurityUtils
from app.db.models.customer import Customer
from app.db.models.equipment import Equipment
from app.db.models.rbac import Site
from app.db.models.service_contract import ServiceContract
from app.services.portal_auth_service import create_portal_user


def _seed_contract(db, company, site, customer):
    c = ServiceContract(
        company_id=company.id,
        customer_id=customer.id,
        contract_number="POL-PORTAL-1",
        name="Contrato portal test",
        default_site_id=site.id,
        allowed_order_kinds=["workshop_intake_contract"],
        template_json={
            "version": 1,
            "fields": [{"key": "location", "label": "Ubicación", "type": "text", "required": True}],
        },
        is_active=True,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def test_contract_crud_and_portal_order(client, db_session, seed_company_and_admin):
    company, admin = seed_company_and_admin
    company.plan = PlanTier.PRO
    db_session.add(company)
    db_session.commit()
    site = db_session.query(Site).filter(Site.company_id == company.id).one()
    customer = Customer(
        company_id=company.id,
        first_name="Portal",
        last_name="Cliente",
        email="portal.client@test.com",
    )
    equipment = Equipment(
        company_id=company.id,
        serial_number="SN-PORTAL",
        brand="Dell",
        model="X1",
    )
    db_session.add_all([customer, equipment])
    db_session.commit()
    db_session.refresh(customer)
    db_session.refresh(equipment)

    admin_token = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "password123"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    created = client.post(
        "/api/v1/service-contracts/",
        headers=headers,
        json={
            "customer_id": str(customer.id),
            "contract_number": "POL-NEW-1",
            "name": "Nuevo contrato",
            "default_site_id": str(site.id),
            "allowed_order_kinds": ["field_service_contract"],
            "template_json": {"version": 1, "fields": []},
        },
    )
    assert created.status_code == 201, created.text

    portal_user = create_portal_user(
        db_session,
        company_id=company.id,
        customer_id=customer.id,
        email="portal.user@test.com",
        full_name="Usuario Portal",
        password="PortalPass123",
        invited_by_id=admin.id,
    )
    db_session.commit()

    contract = _seed_contract(db_session, company, site, customer)

    portal_login = client.post(
        "/api/v1/portal/auth/login",
        json={"email": "portal.user@test.com", "password": "PortalPass123"},
    )
    assert portal_login.status_code == 200, portal_login.text
    portal_headers = {"Authorization": f"Bearer {portal_login.json()['access_token']}"}

    order_res = client.post(
        "/api/v1/portal/orders/",
        headers=portal_headers,
        json={
            "service_contract_id": str(contract.id),
            "order_kind": "workshop_intake_contract",
            "equipment_id": str(equipment.id),
            "problem_description": "Falla reportada desde portal",
            "portal_submitted_json": {"location": "Bodega 3"},
        },
    )
    assert order_res.status_code == 201, order_res.text
    body = order_res.json()
    assert body["order_number"].startswith(f"{site.code}-ITC-")
    assert body["portal_submitted_json"]["location"] == "Bodega 3"

    missing_field = client.post(
        "/api/v1/portal/orders/",
        headers=portal_headers,
        json={
            "service_contract_id": str(contract.id),
            "order_kind": "workshop_intake_contract",
            "equipment_id": str(equipment.id),
            "problem_description": "Sin ubicación",
            "portal_submitted_json": {},
        },
    )
    assert missing_field.status_code == 400
