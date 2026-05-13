"""Contrato del TenantResolverPort: fuentes env vs catálogo y ausencia de queries innecesarias."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from app.tenancy.exceptions import TenantResolveError
from app.tenancy.resolver import DefaultTenantResolver


def test_resolve_by_company_id_uses_env_without_touching_catalog() -> None:
    cid = uuid4()
    fake_url = "sqlite+pysqlite:///:memory:"
    catalog_db = MagicMock()
    resolver = DefaultTenantResolver()

    def _env_only(company_id: UUID) -> str | None:
        return fake_url if company_id == cid else None

    resolver._from_env_map = _env_only  # type: ignore[method-assign]

    info = resolver.resolve_by_company_id(catalog_db, cid)
    assert info.company_id == cid
    assert info.database_url == fake_url
    catalog_db.query.assert_not_called()


def test_resolve_by_company_id_catalog_when_env_empty() -> None:
    cid = uuid4()
    fake_url = "postgresql://u:p@h/db"
    catalog_db = MagicMock()
    row = MagicMock()
    row.database_url = fake_url
    catalog_db.query.return_value.filter.return_value.first.return_value = row

    resolver = DefaultTenantResolver()
    resolver._from_env_map = lambda _cid: None  # type: ignore[method-assign]

    info = resolver.resolve_by_company_id(catalog_db, cid)
    assert info.database_url == fake_url
    catalog_db.query.assert_called_once()


def test_resolve_by_slug_raises_when_inactive() -> None:
    catalog_db = MagicMock()
    row = MagicMock()
    row.is_active = False
    catalog_db.query.return_value.filter.return_value.first.return_value = row

    resolver = DefaultTenantResolver()
    with pytest.raises(TenantResolveError, match="inválido"):
        resolver.resolve_by_slug(catalog_db, "taller-x")


def test_tenant_storage_prefix_shape() -> None:
    from app.core.tenant_storage_paths import tenant_storage_prefix

    cid = uuid4()
    assert tenant_storage_prefix(cid) == f"sgtaller/companies/{cid}"


def test_tenant_resolver_singleton_implements_protocol() -> None:
    from app.tenancy import tenant_resolver
    from app.tenancy.resolver import TenantResolverPort

    assert isinstance(tenant_resolver, TenantResolverPort)
