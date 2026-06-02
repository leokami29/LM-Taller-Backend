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


class OrderDocumentType(str, Enum):
    WORKSHOP_INTAKE = "workshop_intake"
    DELIVERY_RECEIPT = "delivery_receipt"
    WORK_ORDER_SUMMARY = "work_order_summary"


class OrderDocumentFormat(str, Enum):
    A4 = "a4"
    THERMAL = "thermal"


class ServiceOrderKind(str, Enum):
    """Tipo operativo de la orden (define prefijo y serie numérica por sede)."""

    WORKSHOP_INTAKE = "workshop_intake"
    WORKSHOP_INTAKE_CONTRACT = "workshop_intake_contract"
    FIELD_SERVICE = "field_service"
    FIELD_SERVICE_CONTRACT = "field_service_contract"


def is_contract_order_kind(kind: "ServiceOrderKind") -> bool:
    return kind in (
        ServiceOrderKind.WORKSHOP_INTAKE_CONTRACT,
        ServiceOrderKind.FIELD_SERVICE_CONTRACT,
    )


def is_workshop_order_kind(kind: "ServiceOrderKind") -> bool:
    return kind in (
        ServiceOrderKind.WORKSHOP_INTAKE,
        ServiceOrderKind.WORKSHOP_INTAKE_CONTRACT,
    )


class ContractKind(str, Enum):
    MAINTENANCE = "maintenance"
    WARRANTY = "warranty"
    FIELD_SLA = "field_sla"
    CUSTOM = "custom"


PORTAL_ALLOWED_ORDER_KINDS = frozenset(
    {
        ServiceOrderKind.WORKSHOP_INTAKE_CONTRACT,
        ServiceOrderKind.FIELD_SERVICE_CONTRACT,
    }
)


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
