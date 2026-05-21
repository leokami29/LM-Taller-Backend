"""
Semilla de datos de demostración para SGtaller (Postgres / Railway).

Uso (desde la carpeta Backend, con .venv activado y DATABASE_URL en .env):

  python -m scripts.seed_demo
  python -m scripts.seed_demo --force   # borra las empresas demo (NIT 901 y 902) y vuelve a crear

Con USE_TENANT_DATABASE_ROUTING=true: CATALOG_DATABASE_URL + TENANT_DATABASE_URL_MAP_JSON con los UUID de
scripts/seed_demo_constants.py; semilla catálogo y cada BD tenant (slugs demo-central / demo-norte).
Login: tenant_slug + email + Demo1234.

También asegura usuarios de **plataforma** (super_admin, support_readonly, billing) para probar
`/api/platform/v1` y el panel frontend en `/platform`.

Credenciales taller demo (contraseña en todas: Demo1234):
  - admin@demo.sgtaller.com     (admin, todas las sedes)
  - recepcion@demo.sgtaller.com (reception, sede Principal)
  - tecnico1@demo.sgtaller.com    (technician, Principal)
  - tecnico2@demo.sgtaller.com    (technician en Principal + Sede Norte — probar X-Site-Id)
  - visitante@demo.sgtaller.com   (viewer)
  - baja@demo.sgtaller.com        (viewer inactivo)

Planes demo: empresa en plan **Pro** (límites y módulos alineados con `PLAN_DEFAULTS`). Catálogo: fila `subscriptions` plan Pro por taller (routing).

Segundo tenant (misma contraseña Demo1234) — datos normalizados (orden + líneas de costo, inventario, PDFs):
  - admin.norte@demo.sgtaller.com       (admin)
  - recepcion.norte@demo.sgtaller.com   (reception)
  - tecnico.norte@demo.sgtaller.com     (technician)

Plataforma (contraseñas por defecto en dev; ver `scripts/seed_platform.py`):
  - super@sgtaller.com            (super_admin)  default: DevSuper1234
  - support.readonly@demo.sgtaller.com
  - billing@demo.sgtaller.com
"""
from __future__ import annotations

import argparse

from sqlalchemy import select

from app.config import settings
from app.core.security import SecurityUtils
from app.db.models.company import Company
from app.db.session import SessionLocal
from scripts.seed_demo_constants import (
    DEMO_EMAIL_DOMAIN,
    DEMO_NIT,
    DEMO_NITS,
    DEMO_PASSWORD,
    SECOND_COMPANY_NAME,
    SECOND_DEMO_NIT,
)
from scripts.seed_demo_primary import populate_primary_demo_company
from scripts.seed_demo_scenarios import ensure_secondary_demodata
from scripts.seed_platform import ensure_platform_users, platform_dev_credentials_lines
from scripts.seed_utils import delete_company_cascade


def seed_demo(*, force: bool = False) -> None:
    if settings.USE_TENANT_DATABASE_ROUTING:
        from scripts.seed_demo_routed import run_seed_demo_per_tenant

        run_seed_demo_per_tenant(force=force)
        return

    session = SessionLocal()
    try:
        ensure_platform_users(session)

        pwd = SecurityUtils.hash_password(DEMO_PASSWORD)

        existing = session.scalar(select(Company).where(Company.nit_rut == DEMO_NIT))
        if existing and not force:
            print(f"Ya existe la empresa demo (nit {DEMO_NIT}). Usa --force para borrarla y recrearla.")
            ensure_secondary_demodata(session, pwd)
            session.commit()
            print("Usuarios plataforma (ver scripts/seed_platform.py para variables):")
            for line in platform_dev_credentials_lines():
                print(line)
            return

        if existing and force:
            for nit in DEMO_NITS:
                row = session.scalar(select(Company).where(Company.nit_rut == nit))
                if row:
                    delete_company_cascade(session, row.id)

        company = populate_primary_demo_company(session, pwd_hash=pwd, fixed_company_id=None)
        ensure_secondary_demodata(session, pwd)

        session.commit()
        print("Semilla demo creada correctamente.")
        print(f"  Empresa principal: {company.name} (nit {DEMO_NIT})")
        print(f"  Empresa secundaria (multi-tenant): {SECOND_COMPANY_NAME} (nit {SECOND_DEMO_NIT})")
        print(f"  Contraseña usuarios taller demo: {DEMO_PASSWORD}")
        print("  Cuentas taller principal:")
        print(f"    - admin@{DEMO_EMAIL_DOMAIN} (admin)")
        print(f"    - recepcion@{DEMO_EMAIL_DOMAIN} (reception)")
        print(f"    - tecnico1@{DEMO_EMAIL_DOMAIN} (technician)")
        print(f"    - tecnico2@{DEMO_EMAIL_DOMAIN} (technician)")
        print(f"    - visitante@{DEMO_EMAIL_DOMAIN} (viewer)")
        print(f"    - baja@{DEMO_EMAIL_DOMAIN} (viewer) [INACTIVA]")
        print(f"    - portal.cliente@{DEMO_EMAIL_DOMAIN} (portal cliente, slug demo-central)")
        print("  Cuentas taller secundario (902):")
        print(f"    - admin.norte@{DEMO_EMAIL_DOMAIN} (admin)")
        print(f"    - recepcion.norte@{DEMO_EMAIL_DOMAIN} (reception)")
        print(f"    - tecnico.norte@{DEMO_EMAIL_DOMAIN} (technician)")
        print("  Plataforma (/api/platform/v1):")
        for line in platform_dev_credentials_lines():
            print(line)
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sembrar datos demo en Postgres (Railway/local).")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Borra las empresas demo (NIT 901-DEMO-SG y 902-DEMO-SG2) si existen y las vuelve a crear.",
    )
    args = parser.parse_args()
    seed_demo(force=args.force)


if __name__ == "__main__":
    main()
