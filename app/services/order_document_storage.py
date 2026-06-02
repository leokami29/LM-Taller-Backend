"""Almacenamiento local de PDFs de órdenes (Fase 1)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
STORAGE_ROOT = _BACKEND_ROOT / "storage"


def order_document_relative_path(
    *,
    company_id: UUID,
    order_id: UUID,
    document_type: str,
    document_format: str,
) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    filename = f"{document_type}_{document_format}_{ts}.pdf"
    return f"tenants/{company_id}/orders/{order_id}/{filename}"


def order_document_absolute_path(relative_path: str) -> Path:
    return STORAGE_ROOT / relative_path


def save_order_pdf(*, relative_path: str, pdf_bytes: bytes) -> None:
    path = order_document_absolute_path(relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pdf_bytes)


def read_order_pdf(relative_path: str) -> bytes:
    path = order_document_absolute_path(relative_path)
    if not path.is_file():
        raise FileNotFoundError(relative_path)
    return path.read_bytes()
