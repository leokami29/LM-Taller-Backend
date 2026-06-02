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
        rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
        print("alembic_version:", [r[0] for r in rows])

        added = []
        if not _has_column(eng, "sites", "phone"):
            conn.execute(text("ALTER TABLE sites ADD COLUMN phone VARCHAR(30)"))
            added.append("sites.phone")
        if not _has_column(eng, "sites", "email"):
            conn.execute(text("ALTER TABLE sites ADD COLUMN email VARCHAR(255)"))
            added.append("sites.email")
        if not _has_column(eng, "sites", "address_override"):
            conn.execute(text("ALTER TABLE sites ADD COLUMN address_override TEXT"))
            added.append("sites.address_override")
        if not _has_column(eng, "service_orders", "accessories_json"):
            conn.execute(text("ALTER TABLE service_orders ADD COLUMN accessories_json JSONB"))
            added.append("service_orders.accessories_json")
        if not _has_column(eng, "pdf_documents", "revision"):
            conn.execute(text("ALTER TABLE pdf_documents ADD COLUMN revision INTEGER NOT NULL DEFAULT 1"))
            conn.execute(text("ALTER TABLE pdf_documents ALTER COLUMN revision DROP DEFAULT"))
            added.append("pdf_documents.revision")
        if not _has_column(eng, "pdf_documents", "is_copy"):
            conn.execute(text("ALTER TABLE pdf_documents ADD COLUMN is_copy BOOLEAN NOT NULL DEFAULT FALSE"))
            conn.execute(text("ALTER TABLE pdf_documents ALTER COLUMN is_copy DROP DEFAULT"))
            added.append("pdf_documents.is_copy")

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
