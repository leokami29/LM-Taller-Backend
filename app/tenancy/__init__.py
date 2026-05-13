"""Resolución de URL por tenant (contrato + LRU de engines)."""

from app.tenancy.engine_manager import TenantEngineManager, tenant_engine_manager
from app.tenancy.exceptions import TenantResolveError
from app.tenancy.resolver import (
    DefaultTenantResolver,
    TenantResolver,
    TenantResolverPort,
    tenant_resolver,
)
from app.tenancy.types import TenantConnectionInfo

__all__ = [
    "DefaultTenantResolver",
    "TenantConnectionInfo",
    "TenantEngineManager",
    "TenantResolveError",
    "TenantResolver",
    "TenantResolverPort",
    "tenant_engine_manager",
    "tenant_resolver",
]
