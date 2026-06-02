"""Fuerza migración 019 terminando conexiones activas (evita locks de uvicorn)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.config import settings  # noqa

MIGRATION_SQL = [
    "ALTER TABLE sites ADD COLUMN IF NOT EXISTS phone VARCHAR(30)",
    "ALTER TABLE sites ADD COLUMN IF NOT EXISTS email VARCHAR(255)",
    "ALTER TABLE sites ADD COLUMN IF NOT EXISTS address_override TEXT",
    "ALTER TABLE service_orders ADD COLUMN IF NOT EXISTS accessories_json JSONB",
    "ALTER TABLE pdf_documents ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE pdf_documents ADD COLUMN IF NOT EXISTS is_copy BOOLEAN NOT NULL DEFAULT FALSE",
]


def _apply(url: str) -> None:
    from urllib.parse import urlparse

    label = urlparse(url).hostname or url[:20]
    print(f"\n--- {label} ---", flush=True)

    eng = create_engine(
        url,
        connect_args={"connect_timeout": 15},
        isolation_level="AUTOCOMMIT",
    )

    with eng.connect() as conn:
        conn.execute(text("SET lock_timeout = '5s'"))
        conn.execute(text("SET statement_timeout = '60s'"))

        rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
        print("alembic_version:", [r[0] for r in rows], flush=True)

        if "accessories_json" in {c["name"] for c in inspect(eng).get_columns("service_orders")}:
            print("Columnas ya presentes.", flush=True)
        else:
            terminated = conn.execute(
                text(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                      AND pid <> pg_backend_pid()
                    """
                )
            ).fetchall()
            print(f"Conexiones terminadas: {len(terminated)}", flush=True)

            for ddl in MIGRATION_SQL:
                print(f"  ejecutando: {ddl[:60]}...", flush=True)
                conn.execute(text(ddl))

        conn.execute(text("DELETE FROM alembic_version"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('019')"))
        print("alembic_version -> 019  OK", flush=True)


def main() -> None:
    urls: list[str] = []
    if settings.USE_TENANT_DATABASE_ROUTING:
        try:
            m = settings.tenant_database_url_map
        except Exception:
            m = json.loads(settings.TENANT_DATABASE_URL_MAP_JSON or "{}")
        urls.extend(str(u).strip() for u in m.values() if u)
    elif settings.DATABASE_URL:
        urls.append(settings.DATABASE_URL.strip())

    print(f"Forzando migración 019 en {len(urls)} base(s) tenant…", flush=True)
    for url in urls:
        try:
            _apply(url)
        except Exception as exc:
            print(f"  ERROR: {exc}", flush=True)
            raise
    print("\nListo. Reinicie uvicorn.", flush=True)


if __name__ == "__main__":
    main()
