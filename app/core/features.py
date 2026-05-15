"""Catálogo de módulos/features del producto y mapeo permiso → módulo."""

from __future__ import annotations

from app.core.permissions import (
    ADMIN_USERS,
    ANALYTICS_READ,
    CUSTOMERS_DELETE,
    CUSTOMERS_READ,
    CUSTOMERS_WRITE,
    EQUIPMENT_DELETE,
    EQUIPMENT_READ,
    EQUIPMENT_WRITE,
    INVENTORY_DELETE,
    INVENTORY_READ,
    INVENTORY_STOCK,
    INVENTORY_WRITE,
    ORDERS_DELETE,
    ORDERS_READ,
    ORDERS_STATUS,
    ORDERS_WRITE,
)

MODULE_CORE = "core"
MODULE_CUSTOMERS = "customers"
MODULE_EQUIPMENT = "equipment"
MODULE_ORDERS = "orders"
MODULE_INVENTORY = "inventory"
MODULE_ANALYTICS = "analytics"
MODULE_ADMIN_USERS = "admin_users"
MODULE_DOCUMENTS = "documents"

ALL_MODULES = frozenset(
    {
        MODULE_CORE,
        MODULE_CUSTOMERS,
        MODULE_EQUIPMENT,
        MODULE_ORDERS,
        MODULE_INVENTORY,
        MODULE_ANALYTICS,
        MODULE_ADMIN_USERS,
        MODULE_DOCUMENTS,
    }
)

PERMISSION_TO_MODULE: dict[str, str] = {
    CUSTOMERS_READ: MODULE_CUSTOMERS,
    CUSTOMERS_WRITE: MODULE_CUSTOMERS,
    CUSTOMERS_DELETE: MODULE_CUSTOMERS,
    EQUIPMENT_READ: MODULE_EQUIPMENT,
    EQUIPMENT_WRITE: MODULE_EQUIPMENT,
    EQUIPMENT_DELETE: MODULE_EQUIPMENT,
    ORDERS_READ: MODULE_ORDERS,
    ORDERS_WRITE: MODULE_ORDERS,
    ORDERS_STATUS: MODULE_ORDERS,
    ORDERS_DELETE: MODULE_ORDERS,
    INVENTORY_READ: MODULE_INVENTORY,
    INVENTORY_WRITE: MODULE_INVENTORY,
    INVENTORY_STOCK: MODULE_INVENTORY,
    INVENTORY_DELETE: MODULE_INVENTORY,
    ANALYTICS_READ: MODULE_ANALYTICS,
    ADMIN_USERS: MODULE_ADMIN_USERS,
}

PLAN_DEFAULTS: dict[str, dict] = {
    "starter": {
        "modules": {
            MODULE_CORE,
            MODULE_CUSTOMERS,
            MODULE_EQUIPMENT,
            MODULE_ORDERS,
            MODULE_ADMIN_USERS,
        },
        "max_users": 5,
        "max_orders_month": 100,
        "storage_mb": 256,
    },
    "pro": {
        "modules": {
            MODULE_CORE,
            MODULE_CUSTOMERS,
            MODULE_EQUIPMENT,
            MODULE_ORDERS,
            MODULE_INVENTORY,
            MODULE_ANALYTICS,
            MODULE_ADMIN_USERS,
        },
        "max_users": 20,
        "max_orders_month": 2000,
        "storage_mb": 2048,
    },
    "enterprise": {
        "modules": ALL_MODULES,
        "max_users": None,
        "max_orders_month": None,
        "storage_mb": None,
    },
}


def permission_to_module(permission: str) -> str:
    if permission.startswith("documents:"):
        return MODULE_DOCUMENTS
    return PERMISSION_TO_MODULE.get(permission, MODULE_CORE)
