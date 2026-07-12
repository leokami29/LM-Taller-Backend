from app.config import settings
from app.core.security import SecurityUtils
from app.db.models.company import Company
from app.db.models.field_report import FieldReport
from app.db.models.sla_policy import SlaPolicy
from app.db.session import SessionLocal
from scripts.seed_demo import seed_demo


def test_seed_demo_creates_field_reports_and_sla_policies(monkeypatch):
    monkeypatch.setattr(settings, "USE_TENANT_DATABASE_ROUTING", False)
    # Buscar la empresa demo si existe y borrarla para forzar recreación
    session = SessionLocal()
    try:
        from scripts.seed_demo_constants import DEMO_NIT

        existing = session.query(Company).filter(Company.nit_rut == DEMO_NIT).first()
        if existing:
            from scripts.seed_utils import delete_company_cascade

            delete_company_cascade(session, existing.id)
            session.commit()
    finally:
        session.close()

    seed_demo(force=True)

    session = SessionLocal()
    try:
        company = session.query(Company).filter(Company.nit_rut == DEMO_NIT).first()
        assert company is not None
        policies = session.query(SlaPolicy).filter(SlaPolicy.company_id == company.id).all()
        assert len(policies) >= 6
        reports = session.query(FieldReport).filter(FieldReport.company_id == company.id).all()
        assert len(reports) >= 3
    finally:
        session.close()
