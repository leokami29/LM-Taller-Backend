"""Crea un usuario de plataforma super_admin (idempotente por email).

Uso (con venv activo y DATABASE_URL en .env):

    python -m scripts.seed_platform_super_admin

Para crear también support_readonly y billing, usa:

    python -m scripts.seed_demo

Variables opcionales: ver docstring en `scripts/seed_platform.py`.
"""

from __future__ import annotations

from scripts.seed_platform import ensure_super_admin_only_cli


def main() -> None:
    ensure_super_admin_only_cli()


if __name__ == "__main__":
    main()
