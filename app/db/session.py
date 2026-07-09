"""Sesiones SQLAlchemy: monolito (legacy) o catálogo + data plane por tenant."""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.core.security import TYP_PLATFORM, TYP_TENANT, SecurityUtils
from app.db.rls import apply_rls_session_context
from app.tenancy import TenantResolveError, tenant_engine_manager, tenant_resolver

logger = logging.getLogger(__name__)

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=Session)

_catalog_engine = None
_catalog_session_factory: sessionmaker[Session] | None = None


def _catalog_database_url() -> str:
    if settings.USE_TENANT_DATABASE_ROUTING:
        if not settings.CATALOG_DATABASE_URL:
            raise RuntimeError("CATALOG_DATABASE_URL es obligatorio con USE_TENANT_DATABASE_ROUTING=true")
        return settings.CATALOG_DATABASE_URL
    return settings.DATABASE_URL


def _ensure_catalog_engine() -> None:
    global _catalog_engine, _catalog_session_factory
    if _catalog_engine is None:
        _catalog_engine = create_engine(
            _catalog_database_url(),
            echo=settings.DEBUG,
            pool_size=5,
            max_overflow=10,
        )
        _catalog_session_factory = sessionmaker(
            autocommit=False, autoflush=False, bind=_catalog_engine, class_=Session
        )


def _data_plane_company_id_from_authorization(authorization: str | None) -> UUID | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    payload = SecurityUtils.decode_token(authorization[7:].strip())
    if not payload:
        return None
    typ = payload.get("typ")
    if typ == TYP_PLATFORM:
        raw = payload.get("act_as_company_id")
        if not raw:
            return None
        try:
            return UUID(str(raw))
        except ValueError:
            return None
    if typ in (None, TYP_TENANT):
        raw = payload.get("company_id")
        if not raw:
            return None
        try:
            return UUID(str(raw))
        except ValueError:
            return None
    return None


def get_catalog_db(request: Request) -> Generator[Session, None, None]:
    """Sesión contra el catálogo (solo con routing por tenant activo)."""
    if not settings.USE_TENANT_DATABASE_ROUTING:
        raise RuntimeError("get_catalog_db solo está disponible con USE_TENANT_DATABASE_ROUTING=true")
    _ensure_catalog_engine()
    assert _catalog_session_factory is not None
    db = _catalog_session_factory()
    try:
        apply_rls_session_context(db, request.headers.get("Authorization"))
        yield db
    finally:
        db.close()


@contextmanager
def catalog_session_scope() -> Generator[Session, None, None]:
    """Context manager para scripts o login (sin Request)."""
    if not settings.USE_TENANT_DATABASE_ROUTING:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
        return
    _ensure_catalog_engine()
    assert _catalog_session_factory is not None
    db = _catalog_session_factory()
    try:
        yield db
    finally:
        db.close()


def get_db(request: Request) -> Generator[Session, None, None]:
    """Sesión principal: monolito o (catálogo para plataforma | data plane para /api/v1)."""
    if not settings.USE_TENANT_DATABASE_ROUTING:
        db = SessionLocal()
        try:
            apply_rls_session_context(db, request.headers.get("Authorization"))
            yield db
        finally:
            db.close()
        return

    path = request.url.path or ""

    if path.startswith("/api/platform"):
        _ensure_catalog_engine()
        assert _catalog_session_factory is not None
        db = _catalog_session_factory()
        try:
            apply_rls_session_context(db, request.headers.get("Authorization"))
            yield db
        finally:
            db.close()
        return

    if not path.startswith("/api/v1"):
        db = SessionLocal()
        try:
            apply_rls_session_context(db, request.headers.get("Authorization"))
            yield db
        finally:
            db.close()
        return

    company_id = _data_plane_company_id_from_authorization(request.headers.get("Authorization"))
    if company_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de acceso de empresa requerido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _ensure_catalog_engine()
    assert _catalog_session_factory is not None
    cat_db = _catalog_session_factory()
    try:
        try:
            info = tenant_resolver.resolve_by_company_id(cat_db, company_id)
        except TenantResolveError as exc:
            logger.warning("tenant_resolve_failed company_id=%s detail=%s", company_id, exc)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No se pudo resolver la base de datos del taller",
            ) from exc
    finally:
        cat_db.close()

    eng = tenant_engine_manager.get_engine(info.database_url)
    TenantSession = sessionmaker(autocommit=False, autoflush=False, bind=eng, class_=Session)
    db = TenantSession()
    try:
        apply_rls_session_context(db, request.headers.get("Authorization"))
        request.state.tenant_company_id = str(company_id)
        yield db
    finally:
        db.close()


@contextmanager
def tenant_session_for_company(company_id: UUID) -> Generator[Session, None, None]:
    """Abre sesión al data plane del tenant (para refresh u otros flujos sin Request)."""
    if not settings.USE_TENANT_DATABASE_ROUTING:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
        return

    _ensure_catalog_engine()
    assert _catalog_session_factory is not None
    cat_db = _catalog_session_factory()
    try:
        info = tenant_resolver.resolve_by_company_id(cat_db, company_id)
    finally:
        cat_db.close()

    eng = tenant_engine_manager.get_engine(info.database_url)
    TenantSession = sessionmaker(autocommit=False, autoflush=False, bind=eng, class_=Session)
    db = TenantSession()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def tenant_session_for_slug(slug: str) -> Generator[Session, None, None]:
    """Resuelve slug en catálogo y abre sesión al Postgres del taller."""
    if not settings.USE_TENANT_DATABASE_ROUTING:
        raise RuntimeError("tenant_session_for_slug requiere USE_TENANT_DATABASE_ROUTING=true")
    _ensure_catalog_engine()
    assert _catalog_session_factory is not None
    cat_db = _catalog_session_factory()
    try:
        info = tenant_resolver.resolve_by_slug(cat_db, slug)
    finally:
        cat_db.close()

    eng = tenant_engine_manager.get_engine(info.database_url)
    TenantSession = sessionmaker(autocommit=False, autoflush=False, bind=eng, class_=Session)
    db = TenantSession()
    try:
        yield db
    finally:
        db.close()


def decode_refresh_company_id(refresh_token: str) -> Optional[UUID]:
    payload = SecurityUtils.decode_token(refresh_token)
    if not payload or payload.get("token_use") != "refresh":
        return None
    if payload.get("rtyp") != TYP_TENANT and payload.get("typ") != TYP_TENANT:
        return None
    raw = payload.get("company_id")
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except ValueError:
        return None
