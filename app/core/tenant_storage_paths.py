"""Prefijos de object storage acotados por tenant (bucket compartido)."""

from __future__ import annotations

from uuid import UUID


def tenant_storage_prefix(company_id: UUID) -> str:
    """Raíz lógica para keys S3/MinIO de un taller (sin barra final)."""
    return f"sgtaller/companies/{company_id}"
