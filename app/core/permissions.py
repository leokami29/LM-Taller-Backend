"""Permisos recurso:acción para usuarios de empresa (tenant)."""

from __future__ import annotations

from app.core.enums import PlatformRole, UserRole

# Permisos tenant
CUSTOMERS_READ = "customers:read"
CUSTOMERS_WRITE = "customers:write"
CUSTOMERS_DELETE = "customers:delete"
EQUIPMENT_READ = "equipment:read"
EQUIPMENT_WRITE = "equipment:write"
EQUIPMENT_DELETE = "equipment:delete"
ORDERS_READ = "orders:read"
ORDERS_WRITE = "orders:write"
ORDERS_STATUS = "orders:status"
ORDERS_DELETE = "orders:delete"
INVENTORY_READ = "inventory:read"
INVENTORY_WRITE = "inventory:write"
INVENTORY_STOCK = "inventory:stock"
INVENTORY_DELETE = "inventory:delete"
ADMIN_USERS = "admin:users"
ANALYTICS_READ = "analytics:read"
CONTRACTS_READ = "contracts:read"
CONTRACTS_WRITE = "contracts:write"
PORTAL_USERS_READ = "portal_users:read"
PORTAL_USERS_WRITE = "portal_users:write"

TENANT_ROLE_PERMISSIONS: dict[UserRole, frozenset[str]] = {
    UserRole.ADMIN: frozenset(
        {
            CUSTOMERS_READ,
            CUSTOMERS_WRITE,
            CUSTOMERS_DELETE,
            EQUIPMENT_READ,
            EQUIPMENT_WRITE,
            EQUIPMENT_DELETE,
            ORDERS_READ,
            ORDERS_WRITE,
            ORDERS_STATUS,
            ORDERS_DELETE,
            INVENTORY_READ,
            INVENTORY_WRITE,
            INVENTORY_STOCK,
            INVENTORY_DELETE,
            ADMIN_USERS,
            ANALYTICS_READ,
            CONTRACTS_READ,
            CONTRACTS_WRITE,
            PORTAL_USERS_READ,
            PORTAL_USERS_WRITE,
        }
    ),
    UserRole.TECHNICIAN: frozenset(
        {
            CUSTOMERS_READ,
            EQUIPMENT_READ,
            ORDERS_READ,
            ORDERS_WRITE,
            ORDERS_STATUS,
            INVENTORY_READ,
            INVENTORY_STOCK,
            ANALYTICS_READ,
        }
    ),
    UserRole.RECEPTION: frozenset(
        {
            CUSTOMERS_READ,
            CUSTOMERS_WRITE,
            EQUIPMENT_READ,
            EQUIPMENT_WRITE,
            ORDERS_READ,
            ORDERS_WRITE,
            INVENTORY_READ,
            ANALYTICS_READ,
            CONTRACTS_READ,
            PORTAL_USERS_READ,
            PORTAL_USERS_WRITE,
        }
    ),
    UserRole.VIEWER: frozenset(
        {
            CUSTOMERS_READ,
            EQUIPMENT_READ,
            ORDERS_READ,
            INVENTORY_READ,
            ANALYTICS_READ,
        }
    ),
}


def tenant_has_permission(role: UserRole, permission: str) -> bool:
    return permission in TENANT_ROLE_PERMISSIONS.get(role, frozenset())


PLATFORM_COMPANIES_READ = "platform.companies:read"
PLATFORM_COMPANIES_WRITE = "platform.companies:write"
PLATFORM_AUDIT_READ = "platform.audit:read"
PLATFORM_BILLING_READ = "platform.billing:read"
PLATFORM_IMPERSONATE = "platform.impersonate"


PLATFORM_ROLE_PERMISSIONS: dict[PlatformRole, frozenset[str]] = {
    PlatformRole.SUPER_ADMIN: frozenset(
        {
            "*",
            PLATFORM_COMPANIES_READ,
            PLATFORM_COMPANIES_WRITE,
            PLATFORM_AUDIT_READ,
            PLATFORM_BILLING_READ,
            PLATFORM_IMPERSONATE,
        }
    ),
    PlatformRole.SUPPORT_READONLY: frozenset({PLATFORM_COMPANIES_READ, PLATFORM_AUDIT_READ}),
    PlatformRole.BILLING: frozenset({PLATFORM_COMPANIES_READ, PLATFORM_BILLING_READ}),
}


def platform_has_permission(role: PlatformRole, permission: str) -> bool:
    perms = PLATFORM_ROLE_PERMISSIONS.get(role, frozenset())
    return "*" in perms or permission in perms
