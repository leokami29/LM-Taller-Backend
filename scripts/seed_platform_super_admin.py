"""Crea un usuario de plataforma super_admin (idempotente por email).

Uso (con venv activo y DATABASE_URL en .env):

    python -m scripts.seed_platform_super_admin
    python -m scripts.seed_platform_super_admin --force

Con --force, si el usuario ya existe, restablece contraseña (PLATFORM_SUPER_PASSWORD)
y rol super_admin en la BD correcta (catálogo si hay routing multi-tenant).

Para crear también support_readonly y billing, usa:

    python -m scripts.seed_demo

Variables opcionales: ver docstring en `scripts/seed_platform.py`.
"""

from __future__ import annotations

import argparse

from scripts.seed_platform import ensure_super_admin_only_cli


def main() -> None:
    parser = argparse.ArgumentParser(description="Semilla super_admin de plataforma")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Restablecer contraseña y rol si el email ya existe",
    )
    args = parser.parse_args()
    ensure_super_admin_only_cli(force=args.force)


if __name__ == "__main__":
    main()
