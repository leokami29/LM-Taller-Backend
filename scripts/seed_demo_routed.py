"""Semilla demo con USE_TENANT_DATABASE_ROUTING=true: catálogo + 2 Postgres (taller central / norte).

Requiere en .env:
  USE_TENANT_DATABASE_ROUTING=true
  CATALOG_DATABASE_URL=...
  TENANT_DATABASE_URL_MAP_JSON con las claves DEMO_CENTRAL_COMPANY_ID y DEMO_NORTE_COMPANY_ID
  (ver scripts/seed_demo_constants.py).

Uso: python -m scripts.seed_demo [--force]
"""

from __future__ import annotations

import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.core.security import SecurityUtils
from app.db.catalog.models import TenantRouting
from app.db.models.company import Company
from scripts.seed_demo_constants import (
    DEMO_CENTRAL_COMPANY_ID,
    DEMO_CENTRAL_SLUG,
    DEMO_EMAIL_DOMAIN,
    DEMO_NIT,
    DEMO_NORTE_COMPANY_ID,
    DEMO_NORTE_SLUG,
    DEMO_PASSWORD,
    SECOND_COMPANY_NAME,
    SECOND_DEMO_NIT,
)
from scripts.seed_demo_rbac import ensure_demo_catalog_subscriptions
from scripts.seed_demo_primary import populate_primary_demo_company
from scripts.seed_demo_scenarios import ensure_secondary_demodata
from scripts.seed_platform import ensure_platform_users_catalog, platform_dev_credentials_lines
from scripts.seed_utils import delete_company_cascade


def _open_tenant_session(database_url: str):
    eng = create_engine(database_url, pool_pre_ping=True)
    Sess = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    return eng, Sess()


def _wipe_company_by_nit(session, nit: str) -> None:
    row = session.scalar(select(Company).where(Company.nit_rut == nit))
    if row:
        delete_company_cascade(session, row.id)


def _upsert_tenant_routing(
    catalog_db,
    *,
    company_id,
    slug: str,
    database_url: str,
    **fields: object,
) -> None:
    row = catalog_db.get(TenantRouting, company_id)
    if row:
        row.slug = slug
        row.database_url = database_url
        row.is_active = True
        for k, v in fields.items():
            setattr(row, k, v)
    else:
        catalog_db.add(
            TenantRouting(
                company_id=company_id,
                slug=slug,
                database_url=database_url,
                is_active=True,
                **fields,
            )
        )


def run_seed_demo_per_tenant(*, force: bool = False) -> None:
    if not settings.CATALOG_DATABASE_URL:
        print("CATALOG_DATABASE_URL es obligatorio con routing activo.", file=sys.stderr)
        sys.exit(1)
    m = settings.tenant_database_url_map
    kc = str(DEMO_CENTRAL_COMPANY_ID)
    kn = str(DEMO_NORTE_COMPANY_ID)
    if kc not in m or kn not in m:
        print(
            "TENANT_DATABASE_URL_MAP_JSON debe incluir las claves UUID de demo:\n"
            f'  "{kc}": "<URL Postgres BD taller central>"\n'
            f'  "{kn}": "<URL Postgres BD taller norte>"\n'
            "Definidas en scripts/seed_demo_constants.py (DEMO_CENTRAL_COMPANY_ID, DEMO_NORTE_COMPANY_ID).",
            file=sys.stderr,
        )
        sys.exit(1)
    url_central = m[kc]
    url_norte = m[kn]

    pwd = SecurityUtils.hash_password(DEMO_PASSWORD)

    cat_eng = create_engine(settings.CATALOG_DATABASE_URL, pool_pre_ping=True)
    CatSession = sessionmaker(autocommit=False, autoflush=False, bind=cat_eng)
    cdb = CatSession()
    try:
        ensure_platform_users_catalog(cdb)
        _upsert_tenant_routing(
            cdb,
            company_id=DEMO_CENTRAL_COMPANY_ID,
            slug=DEMO_CENTRAL_SLUG,
            database_url=url_central,
            display_name="Taller Central Demo SG",
            nit_rut=DEMO_NIT,
            email=f"contacto@{DEMO_EMAIL_DOMAIN}",
            country="Colombia",
            currency="COP",
            phone="+57 601 5550100",
            address="Carrera 15 # 90-10, Bogotá",
        )
        _upsert_tenant_routing(
            cdb,
            company_id=DEMO_NORTE_COMPANY_ID,
            slug=DEMO_NORTE_SLUG,
            database_url=url_norte,
            display_name=SECOND_COMPANY_NAME,
            nit_rut=SECOND_DEMO_NIT,
            email=f"contacto.norte@{DEMO_EMAIL_DOMAIN}",
            country="Colombia",
            currency="COP",
            phone="+57 601 5550200",
            address="Av. Boyacá # 170, Bogotá",
        )
        ensure_demo_catalog_subscriptions(
            cdb,
            central_company_id=DEMO_CENTRAL_COMPANY_ID,
            norte_company_id=DEMO_NORTE_COMPANY_ID,
        )
        cdb.commit()
        print("[catálogo] platform_users + tenant_routing + subscriptions demo listos.")
    finally:
        cdb.close()
    cat_eng.dispose()

    c_eng, c_sess = _open_tenant_session(url_central)
    try:
        has_c = c_sess.scalar(select(Company).where(Company.nit_rut == DEMO_NIT))
        if has_c and not force:
            print(f"[tenant central] Ya existe empresa demo ({DEMO_NIT}); omitiendo recreación.")
        else:
            if has_c and force:
                _wipe_company_by_nit(c_sess, DEMO_NIT)
            populate_primary_demo_company(
                c_sess, pwd_hash=pwd, fixed_company_id=DEMO_CENTRAL_COMPANY_ID
            )
            print("[tenant central] Dataset principal demo creado.")
        c_sess.commit()
    finally:
        c_sess.close()
        c_eng.dispose()

    n_eng, n_sess = _open_tenant_session(url_norte)
    try:
        has_n = n_sess.scalar(select(Company).where(Company.nit_rut == SECOND_DEMO_NIT))
        if has_n and not force:
            print(f"[tenant norte] Ya existe empresa demo ({SECOND_DEMO_NIT}); omitiendo recreación.")
        else:
            if has_n and force:
                _wipe_company_by_nit(n_sess, SECOND_DEMO_NIT)
            ensure_secondary_demodata(n_sess, pwd, fixed_company_id=DEMO_NORTE_COMPANY_ID)
            print("[tenant norte] Dataset secundario demo creado.")
        n_sess.commit()
    finally:
        n_sess.close()
        n_eng.dispose()

    print("\nLogin tenant (slug + email + contraseña Demo1234):")
    print(f"  Slug central: {DEMO_CENTRAL_SLUG} — admin@{DEMO_EMAIL_DOMAIN}")
    print(f"  Slug norte:   {DEMO_NORTE_SLUG} — admin.norte@{DEMO_EMAIL_DOMAIN}")
    print("  Multi-sede (central): Jorge (tecnico2) tiene rol en Principal y Sede Norte — probá header X-Site-Id.")
    print("  Multi-sede (902): técnico en Principal y Punto Boyacá.")
    print("Plataforma (/api/platform/v1):")
    for line in platform_dev_credentials_lines():
        print(line)
