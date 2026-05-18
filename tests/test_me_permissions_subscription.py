"""Estado de suscripción en GET /me/permissions."""

from datetime import datetime, timedelta, timezone

from app.core.enums import SubscriptionStatus
from app.core.permissions import ADMIN_USERS
from app.db.models.company import Company
from app.services.auth_service import create_tenant_token_pair


def test_me_permissions_suspended_subscription(client, db_session, seed_company_and_admin):
    company, admin = seed_company_and_admin
    company.subscription_status = SubscriptionStatus.SUSPENDED
    db_session.add(company)
    db_session.commit()

    token, _, _ = create_tenant_token_pair(admin, db_session)
    r = client.get(
        "/api/v1/me/permissions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["permissions"] == []
    assert body["entitlements"]["status"] == "suspended"
    assert body["entitlements"]["subscription_usable"] is False


def test_me_permissions_cancelled_subscription(client, db_session, seed_company_and_admin):
    company, admin = seed_company_and_admin
    company.subscription_status = SubscriptionStatus.CANCELLED
    db_session.add(company)
    db_session.commit()

    token, _, _ = create_tenant_token_pair(admin, db_session)
    r = client.get(
        "/api/v1/me/permissions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["permissions"] == []
    assert body["entitlements"]["status"] == "cancelled"
    assert body["entitlements"]["subscription_usable"] is False


def test_me_permissions_active_with_past_period_not_usable(
    client, db_session, seed_company_and_admin, monkeypatch
):
    company, admin = seed_company_and_admin
    past = datetime.now(timezone.utc) - timedelta(days=2)

    def _fake_period_end(_company_id):
        return past

    monkeypatch.setattr(
        "app.services.permission_service.get_catalog_subscription_period_end",
        _fake_period_end,
    )

    token, _, _ = create_tenant_token_pair(admin, db_session)
    r = client.get(
        "/api/v1/me/permissions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["permissions"] == []
    assert body["entitlements"]["subscription_usable"] is False
    assert body["entitlements"]["subscription_block_reason"] == "period_expired"


def test_me_permissions_active_includes_usable_flag(client, db_session, seed_company_and_admin):
    company, admin = seed_company_and_admin
    token, _, _ = create_tenant_token_pair(admin, db_session)
    r = client.get(
        "/api/v1/me/permissions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert ADMIN_USERS in body["permissions"]
    assert body["entitlements"]["subscription_usable"] is True
    assert body["entitlements"]["status"] == "active"
