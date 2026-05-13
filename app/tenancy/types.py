"""Tipos de datos compartidos para resolución de tenant."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class TenantConnectionInfo:
    company_id: UUID
    database_url: str
