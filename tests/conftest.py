import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.core.enums import UserRole
from app.core.security import SecurityUtils
from app.db.base import Base
from app.core.enums import PlanTier, SubscriptionStatus
from app.db.models.company import Company
from app.db.models.rbac import Site, UserSiteRole
from app.db.models.user import User
from app.db.rls import apply_rls_session_context
from app.db.session import get_db
from app.main import app


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(settings.DATABASE_URL)
    return eng


@pytest.fixture(autouse=True)
def _monolith_mode(monkeypatch):
    """Tests usan una sola BD sin tenant_slug en login."""
    monkeypatch.setattr(settings, "USE_TENANT_DATABASE_ROUTING", False)


@pytest.fixture(autouse=True)
def _reset_db(engine):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def db_session(engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    def _override_get_db(request: Request):
        apply_rls_session_context(db_session, request.headers.get("Authorization"))
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seed_company_and_admin(db_session):
    company = Company(
        name="TestCo",
        nit_rut="900000001",
        address="Calle 1",
        plan=PlanTier.PRO,
        subscription_status=SubscriptionStatus.ACTIVE,
        active_users_limit=20,
    )
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)
    site = Site(company_id=company.id, code="MAIN", name="Principal", location="Calle 1")
    db_session.add(site)
    db_session.commit()
    db_session.refresh(site)
    admin = User(
        company_id=company.id,
        email="admin@test.com",
        full_name="Admin",
        hashed_password=SecurityUtils.hash_password("password123"),
        role=UserRole.ADMIN,
    )
    db_session.add(admin)
    db_session.flush()
    db_session.add(
        UserSiteRole(
            user_id=admin.id,
            company_id=company.id,
            site_id=None,
            role=UserRole.ADMIN,
        )
    )
    db_session.commit()
    db_session.refresh(admin)
    return company, admin
