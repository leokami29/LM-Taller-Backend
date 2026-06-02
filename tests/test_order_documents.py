"""PDF comprobantes de ingreso/salida con tracking_code y barcode."""

from app.db.models.customer import Customer
from app.db.models.equipment import Equipment
from app.db.models.pdf_document import PDFDocument
from app.db.models.rbac import Site
from app.db.models.service_order import ServiceOrder
from app.core.tracking_code import allocate_tracking_code
from app.core.enums import OrderDocumentType, OrderDocumentFormat
from app.services.order_document_service import generate_document_pdf, generate_work_order_summary
from app.services.tracking_urls import build_public_tracking_url, resolve_tenant_slug_for_company


def _get_token(client, email="admin@test.com"):
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    ).json()["access_token"]


def _default_site(db_session, company):
    return db_session.query(Site).filter(Site.company_id == company.id).one()


def _seed_order(db_session, company, *, status="received", tracking_code="TG-260099"):
    site = _default_site(db_session, company)
    customer = Customer(
        company_id=company.id,
        first_name="Doc",
        last_name="Test",
        email="doc@test.com",
    )
    equipment = Equipment(
        company_id=company.id,
        serial_number="SN-DOC-1",
        brand="B",
        model="M",
    )
    db_session.add_all([customer, equipment])
    db_session.commit()
    order = ServiceOrder(
        company_id=company.id,
        site_id=site.id,
        order_number="MAIN-IT-DOC-1",
        tracking_code=tracking_code,
        equipment_id=equipment.id,
        current_customer_id=customer.id,
        problem_description="Falla de prueba",
        status=status,
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    return order


def test_tracking_code_unique_per_company(db_session, seed_company_and_admin):
    company, _ = seed_company_and_admin
    c1 = allocate_tracking_code(db_session, company_id=company.id)
    c2 = allocate_tracking_code(db_session, company_id=company.id)
    assert c1 != c2
    assert c1.startswith("TG-")


def test_generate_intake_documents(client, db_session, seed_company_and_admin):
    company, _ = seed_company_and_admin
    order = _seed_order(db_session, company)
    headers = {"Authorization": f"Bearer {_get_token(client)}"}

    r = client.post(
        f"/api/v1/orders/{order.id}/documents",
        headers=headers,
        json={"document_type": "workshop_intake", "format": "a4"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["document_type"] == "workshop_intake"
    assert body["document_format"] == "a4"

    lst = client.get(f"/api/v1/orders/{order.id}/documents", headers=headers)
    assert lst.status_code == 200
    assert len(lst.json()) >= 1

    doc_id = body["id"]
    dl = client.get(
        f"/api/v1/orders/{order.id}/documents/{doc_id}",
        headers=headers,
    )
    assert dl.status_code == 200
    assert dl.content.startswith(b"%PDF")
    assert len(dl.content) > 500

    prev = client.get(
        f"/api/v1/orders/{order.id}/documents/{doc_id}/preview",
        headers=headers,
    )
    assert prev.status_code == 200
    assert prev.headers["content-disposition"] == "inline"


def test_delivery_requires_completed_status(client, db_session, seed_company_and_admin):
    company, _ = seed_company_and_admin
    order = _seed_order(db_session, company, status="received")
    headers = {"Authorization": f"Bearer {_get_token(client)}"}

    bad = client.post(
        f"/api/v1/orders/{order.id}/documents",
        headers=headers,
        json={"document_type": "delivery_receipt", "format": "a4"},
    )
    assert bad.status_code == 400

    order.status = "completed"
    db_session.commit()

    ok = client.post(
        f"/api/v1/orders/{order.id}/documents",
        headers=headers,
        json={"document_type": "delivery_receipt", "format": "thermal"},
    )
    assert ok.status_code == 201
    assert ok.json()["document_format"] == "thermal"


def test_create_order_assigns_tracking_and_intake_pdfs(client, db_session, seed_company_and_admin):
    company, _ = seed_company_and_admin
    site = _default_site(db_session, company)
    customer = Customer(
        company_id=company.id,
        first_name="New",
        last_name="Intake",
        email="new@test.com",
    )
    equipment = Equipment(
        company_id=company.id,
        serial_number="SN-NEW-1",
        brand="X",
        model="Y",
    )
    db_session.add_all([customer, equipment])
    db_session.commit()

    headers = {"Authorization": f"Bearer {_get_token(client)}"}
    created = client.post(
        "/api/v1/orders/",
        headers=headers,
        json={
            "equipment_id": str(equipment.id),
            "current_customer_id": str(customer.id),
            "problem_description": "Problema de ingreso largo",
            "site_id": str(site.id),
            "order_kind": "workshop_intake",
        },
    )
    assert created.status_code == 201
    data = created.json()
    assert data.get("tracking_code")
    assert data["tracking_code"].startswith("TG-")

    docs = (
        db_session.query(PDFDocument)
        .filter(PDFDocument.service_order_id == data["id"])
        .all()
    )
    assert len(docs) >= 2
    types = {d.document_type for d in docs}
    assert "workshop_intake" in types


def test_work_order_summary_pdf_has_codes(db_session, seed_company_and_admin):
    company, _ = seed_company_and_admin
    order = _seed_order(db_session, company)
    slug = resolve_tenant_slug_for_company(company.id)
    pdf = generate_work_order_summary(order, tenant_slug=slug)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 800
    url = build_public_tracking_url(tenant_slug=slug, tracking_code=order.tracking_code, company=company)
    assert "seguimiento" in url


def test_generate_document_pdf_summary(db_session, seed_company_and_admin):
    company, _ = seed_company_and_admin
    order = _seed_order(db_session, company)
    slug = resolve_tenant_slug_for_company(company.id)
    pdf = generate_document_pdf(
        order,
        document_type=OrderDocumentType.WORK_ORDER_SUMMARY,
        format=OrderDocumentFormat.A4.value,
        tenant_slug=slug,
    )
    assert pdf.startswith(b"%PDF")


def test_get_order_by_tracking(client, db_session, seed_company_and_admin):
    company, _ = seed_company_and_admin
    order = _seed_order(db_session, company, tracking_code="TG-269999")
    headers = {"Authorization": f"Bearer {_get_token(client)}"}

    r = client.get("/api/v1/orders/by-tracking/TG-269999", headers=headers)
    assert r.status_code == 200
    assert r.json()["id"] == str(order.id)
