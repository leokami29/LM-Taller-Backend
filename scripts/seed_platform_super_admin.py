"""Crea un usuario de plataforma super_admin (idempotente por email).

Uso (con venv activo y DATABASE_URL en .env):

    python -m scripts.seed_platform_super_admin

Variables opcionales:
    PLATFORM_SUPER_EMAIL  (default: super@sgtaller.com)
    PLATFORM_SUPER_PASSWORD  (obligatorio en producción; en dev default DevSuper1234)
"""

from __future__ import annotations

import os
import sys

from sqlalchemy.orm import Session

from app.core.enums import PlatformRole
from app.core.security import SecurityUtils
from app.db.models.platform_user import PlatformUser
from app.db.session import SessionLocal


def main() -> None:
    email = os.environ.get("PLATFORM_SUPER_EMAIL", "super@sgtaller.com")
    password = os.environ.get("PLATFORM_SUPER_PASSWORD", "DevSuper1234")
    if password == "DevSuper1234" and os.environ.get("ENV") == "production":
        print("Defina PLATFORM_SUPER_PASSWORD en producción.", file=sys.stderr)
        sys.exit(1)

    db: Session = SessionLocal()
    try:
        existing = db.query(PlatformUser).filter(PlatformUser.email == email).first()
        if existing:
            print(f"Ya existe platform user: {email}")
            return
        u = PlatformUser(
            email=email,
            full_name="Super administrador",
            hashed_password=SecurityUtils.hash_password(password),
            role=PlatformRole.SUPER_ADMIN,
        )
        db.add(u)
        db.commit()
        print(f"Creado super_admin plataforma: {email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
