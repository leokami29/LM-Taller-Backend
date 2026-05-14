"""Usuarios de plataforma para desarrollo / pruebas multi-tenant.

Idempotente: no duplica por email. Contraseñas por variables de entorno o valores de dev.

Variables:
  PLATFORM_SUPER_EMAIL, PLATFORM_SUPER_PASSWORD  (super_admin)
  PLATFORM_SUPPORT_EMAIL, PLATFORM_SUPPORT_PASSWORD  (support_readonly)
  PLATFORM_BILLING_EMAIL, PLATFORM_BILLING_PASSWORD  (billing)
  PLATFORM_ROLES_PASSWORD  — contraseña por defecto para support y billing si no definen la suya.
"""

from __future__ import annotations

import os
import sys

from sqlalchemy.orm import Session

from app.core.enums import PlatformRole
from app.core.security import SecurityUtils
from app.db.catalog.models import CatalogPlatformUser
from app.db.models.platform_user import PlatformUser


def _pw(key: str, fallback: str) -> str:
    return os.environ.get(key, fallback)


def _ensure_user(
    session: Session,
    *,
    email: str,
    full_name: str,
    role: PlatformRole,
    password: str,
) -> None:
    existing = session.query(PlatformUser).filter(PlatformUser.email == email).first()
    if existing:
        print(f"  [plataforma] Ya existe: {email} ({existing.role.value})")
        return
    session.add(
        PlatformUser(
            email=email,
            full_name=full_name,
            hashed_password=SecurityUtils.hash_password(password),
            role=role,
        )
    )
    session.flush()
    print(f"  [plataforma] Creado: {email} ({role.value})")


def _ensure_catalog_user(
    session: Session,
    *,
    email: str,
    full_name: str,
    role: PlatformRole,
    password: str,
) -> None:
    existing = session.query(CatalogPlatformUser).filter(CatalogPlatformUser.email == email).first()
    if existing:
        print(f"  [plataforma/catálogo] Ya existe: {email} ({existing.role.value})")
        return
    session.add(
        CatalogPlatformUser(
            email=email,
            full_name=full_name,
            hashed_password=SecurityUtils.hash_password(password),
            role=role,
        )
    )
    session.flush()
    print(f"  [plataforma/catálogo] Creado: {email} ({role.value})")


def ensure_platform_users_catalog(session: Session) -> None:
    """Igual que ensure_platform_users pero en BD catálogo (routing multi-tenant). Hace commit."""
    super_email = _pw("PLATFORM_SUPER_EMAIL", "super@sgtaller.com")
    super_password = _pw("PLATFORM_SUPER_PASSWORD", "DevSuper1234")
    roles_password = _pw("PLATFORM_ROLES_PASSWORD", super_password)
    support_email = _pw("PLATFORM_SUPPORT_EMAIL", "support.readonly@demo.sgtaller.com")
    support_password = _pw("PLATFORM_SUPPORT_PASSWORD", roles_password)
    billing_email = _pw("PLATFORM_BILLING_EMAIL", "billing@demo.sgtaller.com")
    billing_password = _pw("PLATFORM_BILLING_PASSWORD", roles_password)

    if os.environ.get("ENV") == "production" and super_password == "DevSuper1234":
        print("Refuse: en producción defina PLATFORM_SUPER_PASSWORD.", file=sys.stderr)
        sys.exit(1)

    _ensure_catalog_user(
        session,
        email=super_email,
        full_name="Super administrador (seed)",
        role=PlatformRole.SUPER_ADMIN,
        password=super_password,
    )
    _ensure_catalog_user(
        session,
        email=support_email,
        full_name="Soporte solo lectura (seed)",
        role=PlatformRole.SUPPORT_READONLY,
        password=support_password,
    )
    _ensure_catalog_user(
        session,
        email=billing_email,
        full_name="Facturación (seed)",
        role=PlatformRole.BILLING,
        password=billing_password,
    )
    session.commit()


def ensure_platform_users(session: Session) -> None:
    """Crea super_admin + support_readonly + billing si no existen. Hace commit."""
    super_email = _pw("PLATFORM_SUPER_EMAIL", "super@sgtaller.com")
    super_password = _pw("PLATFORM_SUPER_PASSWORD", "DevSuper1234")

    roles_password = _pw("PLATFORM_ROLES_PASSWORD", super_password)
    support_email = _pw("PLATFORM_SUPPORT_EMAIL", "support.readonly@demo.sgtaller.com")
    support_password = _pw("PLATFORM_SUPPORT_PASSWORD", roles_password)
    billing_email = _pw("PLATFORM_BILLING_EMAIL", "billing@demo.sgtaller.com")
    billing_password = _pw("PLATFORM_BILLING_PASSWORD", roles_password)

    if os.environ.get("ENV") == "production" and super_password == "DevSuper1234":
        print(
            "Refuse: en producción defina PLATFORM_SUPER_PASSWORD.",
            file=sys.stderr,
        )
        sys.exit(1)

    _ensure_user(
        session,
        email=super_email,
        full_name="Super administrador (seed)",
        role=PlatformRole.SUPER_ADMIN,
        password=super_password,
    )
    _ensure_user(
        session,
        email=support_email,
        full_name="Soporte solo lectura (seed)",
        role=PlatformRole.SUPPORT_READONLY,
        password=support_password,
    )
    _ensure_user(
        session,
        email=billing_email,
        full_name="Facturación (seed)",
        role=PlatformRole.BILLING,
        password=billing_password,
    )
    session.commit()


def platform_dev_credentials_lines() -> list[str]:
    """Textos para imprimir en consola (sin persistir secretos en código distinto)."""
    super_email = _pw("PLATFORM_SUPER_EMAIL", "super@sgtaller.com")
    super_password = _pw("PLATFORM_SUPER_PASSWORD", "DevSuper1234")
    roles_password = _pw("PLATFORM_ROLES_PASSWORD", super_password)
    support_email = _pw("PLATFORM_SUPPORT_EMAIL", "support.readonly@demo.sgtaller.com")
    support_password = _pw("PLATFORM_SUPPORT_PASSWORD", roles_password)
    billing_email = _pw("PLATFORM_BILLING_EMAIL", "billing@demo.sgtaller.com")
    billing_password = _pw("PLATFORM_BILLING_PASSWORD", roles_password)
    return [
        f"  Plataforma /api/platform/v1 — {super_email} / {super_password} [super_admin]",
        f"  Plataforma — {support_email} / {support_password} [support_readonly]",
        f"  Plataforma — {billing_email} / {billing_password} [billing]",
    ]


def ensure_super_admin_only_cli() -> None:
    """CLI histórico `python -m scripts.seed_platform_super_admin` (solo super_admin)."""
    super_email = _pw("PLATFORM_SUPER_EMAIL", "super@sgtaller.com")
    super_password = _pw("PLATFORM_SUPER_PASSWORD", "DevSuper1234")
    if super_password == "DevSuper1234" and os.environ.get("ENV") == "production":
        print("Defina PLATFORM_SUPER_PASSWORD en producción.", file=sys.stderr)
        sys.exit(1)

    from app.config import settings
    from app.db.session import SessionLocal
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session, sessionmaker

    if settings.USE_TENANT_DATABASE_ROUTING:
        if not settings.CATALOG_DATABASE_URL:
            print("CATALOG_DATABASE_URL es obligatorio con USE_TENANT_DATABASE_ROUTING=true", file=sys.stderr)
            sys.exit(1)
        eng = create_engine(settings.CATALOG_DATABASE_URL)
        Session = sessionmaker(autocommit=False, autoflush=False, bind=eng, class_=Session)
        db = Session()
        try:
            existing = db.query(CatalogPlatformUser).filter(CatalogPlatformUser.email == super_email).first()
            if existing:
                print(f"Ya existe platform user (catálogo): {super_email}")
                return
            db.add(
                CatalogPlatformUser(
                    email=super_email,
                    full_name="Super administrador",
                    hashed_password=SecurityUtils.hash_password(super_password),
                    role=PlatformRole.SUPER_ADMIN,
                )
            )
            db.commit()
            print(f"Creado super_admin plataforma (catálogo): {super_email}")
        finally:
            db.close()
        return

    db = SessionLocal()
    try:
        existing = db.query(PlatformUser).filter(PlatformUser.email == super_email).first()
        if existing:
            print(f"Ya existe platform user: {super_email}")
            return
        _ensure_user(
            db,
            email=super_email,
            full_name="Super administrador",
            role=PlatformRole.SUPER_ADMIN,
            password=super_password,
        )
        db.commit()
        print(f"Creado super_admin plataforma: {super_email}")
    finally:
        db.close()
