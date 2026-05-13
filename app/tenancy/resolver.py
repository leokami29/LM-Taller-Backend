"""Contrato de resolución tenant → URL y implementación por defecto (env + catálogo)."""

from __future__ import annotations

import time
from threading import Lock
from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.db.catalog.models import TenantRouting
from app.tenancy import metrics as tenancy_metrics
from app.tenancy.exceptions import TenantResolveError
from app.tenancy.types import TenantConnectionInfo


@runtime_checkable
class TenantResolverPort(Protocol):
    """Contrato estable: catálogo vs env vs futuro API interno detrás de la misma superficie."""

    def resolve_by_company_id(self, catalog_db: Session, company_id: UUID) -> TenantConnectionInfo:
        ...

    def resolve_by_slug(self, catalog_db: Session, slug: str) -> TenantConnectionInfo:
        ...

    def invalidate_cache(self) -> None:
        ...


class DefaultTenantResolver:
    """Resuelve company_id o slug → URL usando mapa en env y/o filas en catálogo."""

    def __init__(self) -> None:
        self._ttl = max(5, settings.TENANT_RESOLVER_CACHE_TTL_SEC)
        self._cache_slug: dict[str, tuple[float, TenantConnectionInfo]] = {}
        self._cache_company: dict[str, tuple[float, TenantConnectionInfo]] = {}
        self._lock = Lock()

    def _from_env_map(self, company_id: UUID) -> str | None:
        return settings.tenant_database_url_map.get(str(company_id))

    def resolve_by_company_id(self, catalog_db: Session, company_id: UUID) -> TenantConnectionInfo:
        key = str(company_id)
        now = time.monotonic()
        with self._lock:
            hit = self._cache_company.get(key)
            if hit and now - hit[0] < self._ttl:
                tenancy_metrics.bump("resolve_by_company_total")
                tenancy_metrics.bump("resolve_by_company_cache_hit")
                tenancy_metrics.log_resolve_event(
                    method="company_id",
                    company_id=key,
                    cache_hit=True,
                    source="cache",
                )
                return hit[1]

        tenancy_metrics.bump("resolve_by_company_total")
        try:
            url = self._from_env_map(company_id)
            source = "env_map"
            if not url:
                row = (
                    catalog_db.query(TenantRouting)
                    .filter(TenantRouting.company_id == company_id)
                    .first()
                )
                if row and row.database_url:
                    url = row.database_url
                    source = "catalog"
            if not url:
                tenancy_metrics.bump("resolve_errors")
                raise TenantResolveError(f"No hay database_url para company_id={company_id}")

            if source == "env_map":
                tenancy_metrics.bump("resolve_by_company_source_env")
            else:
                tenancy_metrics.bump("resolve_by_company_source_catalog")

            info = TenantConnectionInfo(company_id=company_id, database_url=url)
            with self._lock:
                self._cache_company[key] = (now, info)
            tenancy_metrics.log_resolve_event(
                method="company_id",
                company_id=key,
                cache_hit=False,
                source=source,
            )
            return info
        except TenantResolveError:
            raise
        except Exception:
            tenancy_metrics.bump("resolve_errors")
            raise

    def resolve_by_slug(self, catalog_db: Session, slug: str) -> TenantConnectionInfo:
        slug_key = slug.strip().lower()
        now = time.monotonic()
        with self._lock:
            hit = self._cache_slug.get(slug_key)
            if hit and now - hit[0] < self._ttl:
                tenancy_metrics.bump("resolve_by_slug_total")
                tenancy_metrics.bump("resolve_by_slug_cache_hit")
                tenancy_metrics.log_resolve_event(
                    method="slug",
                    company_id=str(hit[1].company_id),
                    cache_hit=True,
                    source="cache",
                )
                return hit[1]

        tenancy_metrics.bump("resolve_by_slug_total")
        try:
            row = (
                catalog_db.query(TenantRouting)
                .filter(func.lower(TenantRouting.slug) == slug_key)
                .first()
            )
            if not row or not row.is_active:
                tenancy_metrics.bump("resolve_errors")
                raise TenantResolveError("Slug de taller inválido o inactivo")
            url = row.database_url or self._from_env_map(row.company_id)
            if not url:
                tenancy_metrics.bump("resolve_errors")
                raise TenantResolveError("Falta database_url para el slug indicado")
            source = "env_map" if not row.database_url and self._from_env_map(row.company_id) else "catalog"
            info = TenantConnectionInfo(company_id=row.company_id, database_url=url)
            with self._lock:
                self._cache_slug[slug_key] = (now, info)
                self._cache_company[str(row.company_id)] = (now, info)
            tenancy_metrics.log_resolve_event(
                method="slug",
                company_id=str(row.company_id),
                cache_hit=False,
                source=source,
            )
            return info
        except TenantResolveError:
            raise
        except Exception:
            tenancy_metrics.bump("resolve_errors")
            raise

    def invalidate_cache(self) -> None:
        with self._lock:
            self._cache_slug.clear()
            self._cache_company.clear()


tenant_resolver: TenantResolverPort = DefaultTenantResolver()

# Alias retrocompatible con código que importaba `TenantResolver` como clase concreta.
TenantResolver = DefaultTenantResolver
