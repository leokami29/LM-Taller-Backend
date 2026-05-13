"""Ejecuta `alembic upgrade head` contra cada URL listada.

Uso (desde la carpeta Backend, con venv):

  # URLs separadas por coma (laboratorio Railway)
  python -m scripts.migrate_all_tenant_databases --urls "$TENANT_A_URL,$TENANT_B_URL"

  # O leer company_ids desde mapa JSON en entorno TENANT_DATABASE_URL_MAP_JSON
  python -m scripts.migrate_all_tenant_databases --from-env-map

Requiere Alembic del esquema de taller (`alembic.ini` / carpeta `migrations`), no el catálogo.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys


def _urls_from_env_map() -> list[str]:
    raw = os.environ.get("TENANT_DATABASE_URL_MAP_JSON", "{}").strip()
    if not raw:
        return []
    data = json.loads(raw)
    if not isinstance(data, dict):
        return []
    return sorted({str(v) for v in data.values() if v})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--urls",
        help="Lista separada por comas de DATABASE_URL de cada tenant",
        default=None,
    )
    parser.add_argument(
        "--from-env-map",
        action="store_true",
        help="Usa valores únicos de TENANT_DATABASE_URL_MAP_JSON",
    )
    args = parser.parse_args()

    urls: list[str] = []
    if args.urls:
        urls = [u.strip() for u in args.urls.split(",") if u.strip()]
    elif args.from_env_map:
        urls = _urls_from_env_map()
    else:
        print("Indique --urls o --from-env-map", file=sys.stderr)
        sys.exit(1)

    if not urls:
        print("No hay URLs para migrar", file=sys.stderr)
        sys.exit(1)

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for url in urls:
        print(f"Migrando: {url[:24]}...")
        env = os.environ.copy()
        env["DATABASE_URL"] = url
        r = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=root,
            env=env,
            check=False,
        )
        if r.returncode != 0:
            print(f"Falló migración para URL (código {r.returncode})", file=sys.stderr)
            sys.exit(r.returncode)
    print("Migraciones de tenant completadas.")


if __name__ == "__main__":
    main()
