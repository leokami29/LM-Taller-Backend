from contextlib import contextmanager
from datetime import timedelta
from uuid import uuid4

from app.api.v1.endpoints import sync_admin
from app.core.dt import utc_now
from app.core.enums import SubscriptionStatus
from app.core.security import SecurityUtils
from app.db.models.rbac import Site


def _auth_headers(user):
    token = SecurityUtils.create_tenant_access_token(user.id, user.company_id)
    return {"Authorization": f"Bearer {token}"}


def _patch_tenant_session(monkeypatch, db_session, calls):
    @contextmanager
    def fake_tenant_session_for_company(company_id):
        calls.append(company_id)
        yield db_session

    monkeypatch.setattr(sync_admin, "tenant_session_for_company", fake_tenant_session_for_company)


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
