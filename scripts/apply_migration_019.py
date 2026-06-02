"""Aplica migración 019 en todas las bases del mapa TENANT."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects.postgresql import JSONB

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.config import settings  # noqa


def _has_column(eng, table: str, col: str) -> bool:
    return col in {c["name"] for c in inspect(eng).get_columns(table)}


def _apply(url: str) -> None:
    from urllib.parse import urlparse
    label = urlparse(url).hostname or url[:20]
    print(f"\n--- {label} ---", flush=True)
    # connect_args con timeout explícito para evitar colgarse
    connect_args = {"connect_timeout": 15}
    eng = create_engine(url, connect_args=connect_args, pool_timeout=20)
    with eng.begin() as conn:
        # Forzar timeout de lock a 15 s para no colgarse esperando bloqueos
        conn.execute(text("SET LOCAL lock_timeout = '15s'"))
        conn.execute(text("SET LOCAL statement_timeout = '30s'"))

        rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
        print("alembic_version:", [r[0] for r in rows], flush=True)

        added = []
        for table, col, ddl in [
            ("sites", "phone", "ALTER TABLE sites ADD COLUMN IF NOT EXISTS phone VARCHAR(30)"),
            ("sites", "email", "ALTER TABLE sites ADD COLUMN IF NOT EXISTS email VARCHAR(255)"),
            ("sites", "address_override", "ALTER TABLE sites ADD COLUMN IF NOT EXISTS address_override TEXT"),
            ("service_orders", "accessories_json", "ALTER TABLE service_orders ADD COLUMN IF NOT EXISTS accessories_json JSONB"),
            ("pdf_documents", "revision",
             "ALTER TABLE pdf_documents ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 1"),
            ("pdf_documents", "is_copy",
             "ALTER TABLE pdf_documents ADD COLUMN IF NOT EXISTS is_copy BOOLEAN NOT NULL DEFAULT FALSE"),
        ]:
            if not _has_column(eng, table, col):
                conn.execute(text(ddl))
                added.append(f"{table}.{col}")
                print(f"  + {table}.{col}", flush=True)

        conn.execute(text("DELETE FROM alembic_version"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('019')"))

    if added:
        print("Añadido:", added, flush=True)
    else:
        print("Sin cambios en columnas.", flush=True)
    print("alembic_version -> 019  OK", flush=True)


def main() -> None:
    urls = []
    if settings.DATABASE_URL:
        urls.append(settings.DATABASE_URL.strip())
    if settings.USE_TENANT_DATABASE_ROUTING:
        try:
            m = settings.tenant_database_url_map
        except Exception:
            m = json.loads(settings.TENANT_DATABASE_URL_MAP_JSON or "{}")
        for u in m.values():
            if u and str(u).strip() not in urls:
                urls.append(str(u).strip())

    print(f"Aplicando migración 019 en {len(urls)} base(s)…", flush=True)
    for url in urls:
        try:
            _apply(url)
        except Exception as exc:
            print(f"  ERROR: {exc}", flush=True)
    print("\nListo. Reinicie uvicorn.", flush=True)


if __name__ == "__main__":
    main()
