from datetime import timedelta

from app.core.dt import utc_now
from app.core.enums import UserRole
from app.core.permissions import ADMIN_USERS, ORDERS_WRITE
from app.core.security import SecurityUtils
from app.db.models.rbac import TemporaryPermission, UserSiteRole
from app.db.models.user import User
from app.services.permission_service import PermissionService


def test_admin_has_admin_users_permission(db_session, seed_company_and_admin):
    company, admin = seed_company_and_admin
    svc = PermissionService(db_session)
    assert svc.has_permission(admin.id, company.id, ADMIN_USERS) is True


def test_viewer_cannot_write_orders(db_session, seed_company_and_admin):
    company, admin = seed_company_and_admin
    viewer = User(
        company_id=company.id,
        email="viewer@test.com",
        full_name="Viewer",
        hashed_password=SecurityUtils.hash_password("password123"),
        role=UserRole.VIEWER,
    )
    db_session.add(viewer)
    db_session.flush()
    db_session.add(
        UserSiteRole(
            user_id=viewer.id,
            company_id=company.id,
            site_id=None,
            role=UserRole.VIEWER,
        )
    )
    db_session.commit()
    svc = PermissionService(db_session)
    assert svc.has_permission(viewer.id, company.id, ORDERS_WRITE) is False


def test_temporary_permission_grants_access(db_session, seed_company_and_admin):
    company, admin = seed_company_and_admin
    viewer = User(
        company_id=company.id,
        email="temp@test.com",
        full_name="Temp",
        hashed_password=SecurityUtils.hash_password("password123"),
        role=UserRole.VIEWER,
    )
    db_session.add(viewer)
    db_session.flush()
    db_session.add(
        UserSiteRole(user_id=viewer.id, company_id=company.id, site_id=None, role=UserRole.VIEWER)
    )
    db_session.add(
        TemporaryPermission(
            user_id=viewer.id,
            company_id=company.id,
            permission=ORDERS_WRITE,
            expires_at=utc_now() + timedelta(days=1),
            granted_by_id=admin.id,
        )
    )
    db_session.commit()
    svc = PermissionService(db_session)
    assert svc.has_permission(viewer.id, company.id, ORDERS_WRITE) is True


def test_can_add_user_limit(db_session, seed_company_and_admin):
    company, _admin = seed_company_and_admin
    svc = PermissionService(db_session)
    for i in range(20):
        u = User(
            company_id=company.id,
            email=f"u{i}@test.com",
            full_name=f"U{i}",
            hashed_password="x",
            role=UserRole.VIEWER,
            is_active=True,
        )
        db_session.add(u)
    db_session.commit()
    ok, _ = svc.can_add_user(company.id)
    assert ok is False


def test_me_permissions_endpoint(client, seed_company_and_admin):
    company, admin = seed_company_and_admin
    token, _ = __import__(
        "app.services.auth_service", fromlist=["create_tenant_token_pair"]
    ).create_tenant_token_pair(admin)
    r = client.get(
        "/api/v1/me/permissions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert ADMIN_USERS in body["permissions"]
    assert body["entitlements"]["plan"] == "pro"
