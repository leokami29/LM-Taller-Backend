"""Entorno Alembic para el catálogo (control plane)."""

from logging.config import fileConfig
from pathlib import Path

from dotenv import load_dotenv

# Cargar Backend/.env antes de settings (Alembic a veces se ejecuta con cwd distinto).
_backend_root = Path(__file__).resolve().parents[1]
load_dotenv(_backend_root / ".env")

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.db.catalog.base import CatalogBase
import app.db.catalog.models  # noqa: F401

config = context.config
url = settings.CATALOG_DATABASE_URL or ""
config.set_main_option("sqlalchemy.url", url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = CatalogBase.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    if not url:
        raise RuntimeError(
            "CATALOG_DATABASE_URL debe estar definido para migraciones del catálogo. "
            f"Añádelo en {_backend_root / '.env'} (URL del Postgres catálogo; desde fuera de Railway suele "
            "llevar ?sslmode=require) o exporta la variable en la shell antes de ejecutar Alembic."
        )
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
