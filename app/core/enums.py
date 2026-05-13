from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    TECHNICIAN = "technician"
    RECEPTION = "reception"
    VIEWER = "viewer"


class PlatformRole(str, Enum):
    """Roles del equipo licenciante (acceso global a la plataforma)."""

    SUPER_ADMIN = "super_admin"
    SUPPORT_READONLY = "support_readonly"
    BILLING = "billing"


class OrderStatus(str, Enum):
    RECEIVED = "received"
    DIAGNOSING = "diagnosing"
    WAITING_PARTS = "waiting_parts"
    IN_REPAIR = "in_repair"
    COMPLETED = "completed"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class OrderPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class InventoryMovementType(str, Enum):
    PURCHASE = "purchase"
    USED_IN_REPAIR = "used_in_repair"
    SALE = "sale"
    ADJUSTMENT = "adjustment"
    DAMAGE = "damage"


class IdentificationType(str, Enum):
    CC = "CC"
    NIT = "NIT"
    PASSPORT = "Passport"
    CEDULA_EXTRANJERIA = "Cédula Extranjería"
