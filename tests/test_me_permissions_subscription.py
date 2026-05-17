"""Estado de suscripción en GET /me/permissions."""

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
