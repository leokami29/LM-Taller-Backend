"""Exporta datos de una empresa desde la BD monolítica (referencia).

Este script documenta el enfoque; la extracción completa depende de las tablas
con `company_id`. Flujo típico:

1. Crear BD vacía del tenant y correr `alembic upgrade head` contra esa URL.
2. Ejecutar este script en modo `--dry-run` para listar conteos por tabla.
3. Implementar inserciones ordenadas respetando FKs (o usar pg_dump filtrado).

Uso:

  python -m scripts.export_company_to_tenant_db --company-id <UUID> --dry-run

Variables: DATABASE_URL apunta al monolito origen.
"""

from __future__ import annotations

import argparse
import sys
from uuid import UUID

from sqlalchemy import create_engine, func, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company-id", type=str, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        company_id = UUID(args.company_id)
    except ValueError:
        print("company-id inválido", file=sys.stderr)
        sys.exit(1)

    eng = create_engine(settings.DATABASE_URL)
    insp = inspect(eng)
    tables = insp.get_table_names()
    SessionLocal = sessionmaker(bind=eng)
    db: Session = SessionLocal()
    try:
        for table in sorted(tables):
            cols = {c["name"] for c in insp.get_columns(table)}
            if "company_id" not in cols:
                continue
            q = text(f'SELECT COUNT(*) AS c FROM "{table}" WHERE company_id = :cid')
            count = db.execute(q, {"cid": str(company_id)}).scalar()
            print(f"{table}: {count} filas")
        if args.dry_run:
            print("(dry-run: no se escribió destino)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
