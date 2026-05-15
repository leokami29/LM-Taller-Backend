"""Migraciones Alembic: tenant (app) y catálogo (control plane).

Uso desde la carpeta Backend con el venv activado:

  python -m scripts.migrate diagnose
  python -m scripts.migrate tenant
  python -m scripts.migrate catalog
  python -m scripts.migrate all

No uses ``migrations_catalog/alembic.ini`` — el archivo correcto es ``alembic_catalog.ini`` en la raíz de Backend.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
TENANT_REVISIONS = {
    "001_initial",
    "002_multi_tenant",
    "003_schema_indexes",
    "004_cost_lines",
    "005_company_triggers",
    "006_cross_table_company",
    "007_used_in_repair_check",
    "008_customer_rut_notes",
    "009_customer_search_idx",
    "010_rbac_multisite",
}
CATALOG_REVISIONS = {"catalog_001", "catalog_002"}


def _same_database_url(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return a.strip().rstrip("/") == b.strip().rstrip("/")


def _tenant_urls_from_settings(settings) -> list[str]:
    m = getattr(settings, "tenant_database_url_map", None) or {}
    return sorted({str(v) for v in m.values() if v})


def _run_tenant_migrations_for_urls(urls: list[str]) -> int:
    import os

    if not urls:
        print("No hay URLs de tenant en el mapa.")
        return 1
    for url in urls:
        safe = url.split("@")[-1] if "@" in url else url[:32]
        print(f"Migrando tenant … @{safe}")
        env = os.environ.copy()
        env["DATABASE_URL"] = url
        r = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_ROOT,
            env=env,
            check=False,
        )
        if r.returncode != 0:
            print(f"Falló migración tenant (código {r.returncode})", file=sys.stderr)
            return r.returncode
    print("Migraciones de tenant completadas.")
    return 0


def _load_settings():
    from dotenv import load_dotenv

    load_dotenv(BACKEND_ROOT / ".env")
    from app.config import settings

    return settings


def _read_version(database_url: str) -> str | None:
    engine = create_engine(database_url)
    with engine.connect() as conn:
        try:
            row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
        except Exception:
            return None
    return str(row[0]) if row else None


def diagnose() -> int:
    settings = _load_settings()
    print("=== Diagnóstico Alembic ===\n")

    if not settings.DATABASE_URL:
        print("DATABASE_URL no está definido en .env")
        return 1

    tenant_ver = _read_version(settings.DATABASE_URL)
    catalog_same = _same_database_url(settings.DATABASE_URL, settings.CATALOG_DATABASE_URL)

    label = "DATABASE_URL (= catálogo en tu setup)"
    if not catalog_same:
        label = "DATABASE_URL"

    print(f"{label}: versión = {tenant_ver or '(sin tabla alembic_version)'}")

    if tenant_ver:
        if tenant_ver in CATALOG_REVISIONS:
            if catalog_same and getattr(settings, "USE_TENANT_DATABASE_ROUTING", False):
                print(
                    "\nOK: Esta URL es la BD de CATÁLOGO (DATABASE_URL la reutilizás para rutas globales).\n"
                    "Versión catalog_* es correcta aquí.\n"
                    "Migraciones del ESQUEMA DE TALLER van solo a las URLs del mapa:\n"
                    "  python -m scripts.migrate_all_tenant_databases --from-env-map\n"
                )
            else:
                print(
                    "\nERROR: Esta base tiene una revisión de CATÁLOGO en alembic_version,\n"
                    "pero DATABASE_URL debería ser la BD del TALLER (data plane).\n"
                    "\nOpciones:\n"
                    "  1) Si DATABASE_URL es la BD catálogo por error → corrige .env.\n"
                    "  2) Si aplicaste migraciones de catálogo en la BD tenant por error:\n"
                    "     python -m alembic stamp 009_customer_search_idx\n"
                    "     python -m alembic upgrade head\n"
                )
                return 1
        elif tenant_ver not in TENANT_REVISIONS:
            print(f"\nAVISO: revisión '{tenant_ver}' no está en la lista conocida de tenant.")

    tenant_urls = _tenant_urls_from_settings(settings)
    print(f"\nTalleres en TENANT_DATABASE_URL_MAP_JSON: {len(tenant_urls)} URL(s) distinta(s).")

    if settings.CATALOG_DATABASE_URL:
        cat_ver = _read_version(settings.CATALOG_DATABASE_URL)
        print(f"\nCATALOG_DATABASE_URL: versión = {cat_ver or '(sin tabla alembic_version)'}")
        if cat_ver and cat_ver in TENANT_REVISIONS:
            print(
                "\nAVISO: El catálogo tiene una revisión de TENANT. Usa solo:\n"
                "  python -m scripts.migrate catalog\n"
            )
    else:
        print("\nCATALOG_DATABASE_URL no definido (opcional si USE_TENANT_DATABASE_ROUTING=false).")

    print("\nComandos correctos:")
    print("  python -m alembic -c alembic_catalog.ini upgrade head   # catálogo")
    print("  python -m scripts.migrate_all_tenant_databases --from-env-map   # cada taller")
    print("  python -m scripts.migrate all   # catálogo + talleres del mapa (si .env cargado)")
    print("  python -m alembic upgrade head   # solo si DATABASE_URL es una BD tenant dedicada")
    return 0


def _run_alembic(ini_name: str, extra_env: dict[str, str] | None = None) -> int:
    env = None
    if extra_env:
        import os

        env = os.environ.copy()
        env.update(extra_env)
    cmd = [sys.executable, "-m", "alembic", "-c", ini_name, "upgrade", "head"]
    print(f"Ejecutando: {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=BACKEND_ROOT, env=env, check=False)
    return r.returncode


def migrate_tenant() -> int:
    settings = _load_settings()
    ver = _read_version(settings.DATABASE_URL) if settings.DATABASE_URL else None
    if ver in CATALOG_REVISIONS and _same_database_url(settings.DATABASE_URL, settings.CATALOG_DATABASE_URL):
        print(
            "DATABASE_URL apunta al catálogo (misma URL que CATALOG_DATABASE_URL).\n"
            "No ejecutes aquí `alembic upgrade head` del esquema de taller.\n"
            "Usa:\n"
            "  python -m scripts.migrate_all_tenant_databases --from-env-map"
        )
        return 1
    if ver in CATALOG_REVISIONS:
        print(
            f"Abortado: DATABASE_URL tiene revisión de catálogo ({ver}). "
            "Ejecuta: python -m scripts.migrate diagnose"
        )
        return 1
    return _run_alembic("alembic.ini")


def migrate_catalog() -> int:
    settings = _load_settings()
    if not settings.CATALOG_DATABASE_URL:
        print(
            "CATALOG_DATABASE_URL no está en .env.\n"
            "Defínela (Postgres del catálogo) y vuelve a ejecutar."
        )
        return 1
    return _run_alembic("alembic_catalog.ini", {"DATABASE_URL": settings.CATALOG_DATABASE_URL})


def migrate_all() -> int:
    settings = _load_settings()
    if settings.CATALOG_DATABASE_URL:
        code = migrate_catalog()
        if code != 0:
            return code

    same = _same_database_url(settings.DATABASE_URL, settings.CATALOG_DATABASE_URL)
    if settings.USE_TENANT_DATABASE_ROUTING and same:
        urls = _tenant_urls_from_settings(settings)
        if not urls:
            print("AVISO: TENANT_DATABASE_URL_MAP_JSON vacío; no hay BDs tenant que migrar.")
            return 0
        return _run_tenant_migrations_for_urls(urls)

    code = migrate_tenant()
    if code != 0:
        return code
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Migraciones tenant y catálogo")
    parser.add_argument(
        "command",
        choices=("diagnose", "tenant", "catalog", "all"),
        help="diagnose | tenant | catalog | all",
    )
    args = parser.parse_args()
    handlers = {
        "diagnose": diagnose,
        "tenant": migrate_tenant,
        "catalog": migrate_catalog,
        "all": migrate_all,
    }
    sys.exit(handlers[args.command]())


if __name__ == "__main__":
    main()
