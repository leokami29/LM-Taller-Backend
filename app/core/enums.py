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


class CostLineCategory(str, Enum):
    """Clasificación de una línea de costo en una orden (desglose normalizado)."""

    PARTS = "parts"
    LABOR = "labor"
    OTHER = "other"


class IdentificationType(str, Enum):
    CC = "CC"
    NIT = "NIT"
    RUT = "RUT"
    PASSPORT = "Passport"
    CEDULA_EXTRANJERIA = "Cédula Extranjería"


class PlanTier(str, Enum):
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    TRIAL = "trial"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class RoleChangeStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
