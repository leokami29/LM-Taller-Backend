"""Aplica esquema migración 018 en DATABASE_URL y en cada BD tenant del mapa."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.config import settings  # noqa: E402


def _db_label(url: str) -> str:
    p = urlparse(url)
    return f"{p.hostname or '?'}:{p.port or ''}/{ (p.path or '/').lstrip('/') }"


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in inspector.get_table_names():
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def _apply_018(url: str) -> None:
    print(f"\n--- {_db_label(url)} ---")
    engine = create_engine(url)
    inspector = inspect(engine)

    with engine.begin() as conn:
        rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
        print("alembic_version:", [r[0] for r in rows])

    inspector = inspect(engine)
    with engine.begin() as conn:
        if "order_tracking_sequences" not in inspector.get_table_names():
            conn.execute(
                text(
                    """
                    CREATE TABLE order_tracking_sequences (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        company_id UUID NOT NULL REFERENCES companies(id),
                        next_value INTEGER NOT NULL DEFAULT 1,
                        CONSTRAINT uq_order_tracking_sequences_company UNIQUE (company_id)
                    )
                    """
                )
            )
            print("+ order_tracking_sequences")

        if not _has_column(inspector, "service_orders", "tracking_code"):
            conn.execute(text("ALTER TABLE service_orders ADD COLUMN tracking_code VARCHAR(16)"))
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_service_orders_tracking_code "
                    "ON service_orders (company_id, tracking_code)"
                )
            )
            print("+ service_orders.tracking_code")
        else:
            print("= tracking_code ya existe")

        if "pdf_documents" in inspector.get_table_names() and not _has_column(
            inspector, "pdf_documents", "document_format"
        ):
            conn.execute(
                text(
                    "ALTER TABLE pdf_documents "
                    "ADD COLUMN document_format VARCHAR(16) NOT NULL DEFAULT 'a4'"
                )
            )
            conn.execute(text("ALTER TABLE pdf_documents ALTER COLUMN document_format DROP DEFAULT"))
            print("+ pdf_documents.document_format")

        conn.execute(text("DELETE FROM alembic_version"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('018')"))

    inspector = inspect(engine)
    ok = _has_column(inspector, "service_orders", "tracking_code")
    print("OK" if ok else "FALLO: sin tracking_code")


def _collect_urls() -> list[str]:
    urls: list[str] = []
    if settings.DATABASE_URL:
        urls.append(settings.DATABASE_URL.strip())
    if settings.USE_TENANT_DATABASE_ROUTING:
        try:
            m = settings.tenant_database_url_map
        except Exception:
            raw = settings.TENANT_DATABASE_URL_MAP_JSON.strip() or "{}"
            m = json.loads(raw)
        for u in m.values():
            if u:
                urls.append(str(u).strip())
    # únicos preservando orden
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def main() -> None:
    print("USE_TENANT_DATABASE_ROUTING:", settings.USE_TENANT_DATABASE_ROUTING)
    urls = _collect_urls()
    if not urls:
        print("No hay DATABASE_URL en .env")
        sys.exit(1)
    print(f"Bases a actualizar: {len(urls)}")
    for url in urls:
        _apply_018(url)
    print("\nListo. Reinicie uvicorn.")


if __name__ == "__main__":
    main()
