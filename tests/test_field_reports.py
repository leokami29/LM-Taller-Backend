from app.core.enums import UserRole
from app.core.security import SecurityUtils
from app.db.models.user import User


def _login(client, email="admin@test.com", password="password123"):
    res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200
    return res.json()["access_token"]


def test_create_and_list_field_reports(client, seed_company_and_admin):
    company, admin = seed_company_and_admin
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    create_res = client.post(
        "/api/v1/field-reports/",
        headers=headers,
        json={
            "title": "Visita de diagnóstico",
            "findings": "Equipo no enciende por fuente",
            "recommendations": "Reemplazar fuente de poder",
            "status": "draft",
        },
    )
    assert create_res.status_code == 201
    data = create_res.json()
    assert data["title"] == "Visita de diagnóstico"
    assert data["findings"] == "Equipo no enciende por fuente"
    assert data["technician_id"] == str(admin.id)
    assert data["status"] == "draft"

    list_res = client.get("/api/v1/field-reports/", headers=headers)
    assert list_res.status_code == 200
    payload = list_res.json()
    assert payload["total"] == 1
    assert len(payload["items"]) == 1


def test_get_field_report(client, seed_company_and_admin):
    company, admin = seed_company_and_admin
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    create_res = client.post(
        "/api/v1/field-reports/",
        headers=headers,
        json={"title": "Reporte detalle"},
    )
    report_id = create_res.json()["id"]

    get_res = client.get(f"/api/v1/field-reports/{report_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == report_id

    missing = client.get("/api/v1/field-reports/00000000-0000-0000-0000-000000000000", headers=headers)
    assert missing.status_code == 404


def test_update_field_report(client, seed_company_and_admin):
    company, admin = seed_company_and_admin
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    create_res = client.post(
        "/api/v1/field-reports/",
        headers=headers,
        json={"title": "Original"},
    )
    report_id = create_res.json()["id"]

    update_res = client.put(
        f"/api/v1/field-reports/{report_id}",
        headers=headers,
        json={"title": "Actualizado", "status": "submitted"},
    )
    assert update_res.status_code == 200
    data = update_res.json()
    assert data["title"] == "Actualizado"
    assert data["status"] == "submitted"


def test_delete_field_report(client, seed_company_and_admin):
    company, admin = seed_company_and_admin
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    create_res = client.post(
        "/api/v1/field-reports/",
        headers=headers,
        json={"title": "Para eliminar"},
    )
    report_id = create_res.json()["id"]

    del_res = client.delete(f"/api/v1/field-reports/{report_id}", headers=headers)
    assert del_res.status_code == 204

    get_res = client.get(f"/api/v1/field-reports/{report_id}", headers=headers)
    assert get_res.status_code == 404


def test_field_report_permissions(client, db_session, seed_company_and_admin):
    company, admin = seed_company_and_admin
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
        "/api/v1/field-reports/",
        headers=viewer_headers,
        json={"title": "No debería crear"},
    )
    assert create_res.status_code == 403

    admin_token = _login(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    report_res = client.post(
        "/api/v1/field-reports/",
        headers=admin_headers,
        json={"title": "Reporte visible"},
    )
    report_id = report_res.json()["id"]

    get_res = client.get(f"/api/v1/field-reports/{report_id}", headers=viewer_headers)
    assert get_res.status_code == 200
