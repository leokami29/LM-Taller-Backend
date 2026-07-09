from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.models.user import User
from app.schemas.license import SignedLicenseManifest

SyncEntity = Literal[
    "company",
    "site",
    "user",
    "user_site_role",
    "session_policy",
    "role_change_request",
    "temporary_permission",
    "audit_log",
    "customer",
    "equipment",
    "service_order",
    "inventory_item",
    "service_contract",
]
SyncOp = Literal["create", "update", "delete", "deactivate", "reset_password", "status_change", "stock_change"]


class AdminMutation(BaseModel):
    mutation_id: UUID = Field(default_factory=uuid4)
    entity: SyncEntity
    entity_id: UUID
    op: SyncOp
    updated_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class AdminPushRequest(BaseModel):
    mutations: list[AdminMutation] = Field(default_factory=list)


class AdminPushItemResult(BaseModel):
    mutation_id: UUID
    entity: SyncEntity
    entity_id: UUID
    status: Literal["applied", "rejected", "conflict"]
    detail: str = ""


class AdminPushResponse(BaseModel):
    results: list[AdminPushItemResult]
    cursor: str


class AdminSyncSnapshot(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    company_id: UUID
    cursor: str
    company: dict[str, Any]
    sites: list[dict[str, Any]]
    users: list[dict[str, Any]]
    user_site_roles: list[dict[str, Any]]
    entitlements: dict[str, Any]
    license_manifest: SignedLicenseManifest | None = None
    customers: list[dict[str, Any]] = Field(default_factory=list)
    equipment: list[dict[str, Any]] = Field(default_factory=list)
    equipment_attributes: list[dict[str, Any]] = Field(default_factory=list)
    service_orders: list[dict[str, Any]] = Field(default_factory=list)
    service_order_images: list[dict[str, Any]] = Field(default_factory=list)
    inventory_categories: list[dict[str, Any]] = Field(default_factory=list)
    inventory_items: list[dict[str, Any]] = Field(default_factory=list)
    inventory_movements: list[dict[str, Any]] = Field(default_factory=list)
    service_contracts: list[dict[str, Any]] = Field(default_factory=list)
    role_change_requests: list[dict[str, Any]] = Field(default_factory=list)
    temporary_permissions: list[dict[str, Any]] = Field(default_factory=list)
    audit_logs: list[dict[str, Any]] = Field(default_factory=list)


@dataclass
class SyncContext:
    db: Session
    user: User
    company_id: UUID
    permissions: frozenset[str]
