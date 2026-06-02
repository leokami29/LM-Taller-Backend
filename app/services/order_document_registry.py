"""Registro y persistencia de PDFDocument para órdenes."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.core.enums import OrderDocumentFormat, OrderDocumentType, OrderStatus, is_workshop_order_kind
from app.db.models.pdf_document import PDFDocument
from app.db.models.service_order import ServiceOrder
from app.db.models.user import User
from app.core.tracking_code import ensure_order_tracking_code
from app.services.order_document_service import generate_document_pdf
from app.services.tracking_urls import resolve_tenant_slug_for_company
from app.services.order_document_storage import (
    order_document_relative_path,
    read_order_pdf,
    save_order_pdf,
)

logger = logging.getLogger(__name__)


def load_order_for_documents(db: Session, *, company_id: UUID, order_id: UUID) -> ServiceOrder | None:
    return (
        db.query(ServiceOrder)
        .options(
            joinedload(ServiceOrder.company),
            joinedload(ServiceOrder.site),
            joinedload(ServiceOrder.current_customer),
            joinedload(ServiceOrder.equipment),
            joinedload(ServiceOrder.received_by),
            joinedload(ServiceOrder.assigned_technician),
            joinedload(ServiceOrder.cost_lines),
            joinedload(ServiceOrder.timeline_entries),
        )
        .filter(ServiceOrder.id == order_id, ServiceOrder.company_id == company_id)
        .first()
    )


def list_order_documents(db: Session, *, order_id: UUID) -> list[PDFDocument]:
    return (
        db.query(PDFDocument)
        .filter(PDFDocument.service_order_id == order_id)
        .order_by(PDFDocument.generated_at.desc())
        .all()
    )


def create_order_document(
    db: Session,
    *,
    order: ServiceOrder,
    document_type: OrderDocumentType,
    document_format: OrderDocumentFormat,
    generated_by: User,
) -> PDFDocument:
    if document_type == OrderDocumentType.DELIVERY_RECEIPT and order.status not in (
        OrderStatus.COMPLETED,
        OrderStatus.DELIVERED,
    ):
        raise ValueError("El comprobante de salida requiere orden completada o entregada")

    # Calcular revisión: cuántos documentos del mismo tipo+formato ya existen
    existing_count = (
        db.query(PDFDocument)
        .filter(
            PDFDocument.service_order_id == order.id,
            PDFDocument.document_type == document_type.value,
            PDFDocument.document_format == document_format.value,
        )
        .count()
    )
    revision = existing_count + 1
    is_copy = existing_count > 0

    ensure_order_tracking_code(db, order)
    tenant_slug = resolve_tenant_slug_for_company(order.company_id)

    pdf_bytes = generate_document_pdf(
        order,
        document_type=document_type,
        format=document_format.value,
        revision=revision,
        tenant_slug=tenant_slug,
    )
    rel_path = order_document_relative_path(
        company_id=order.company_id,
        order_id=order.id,
        document_type=document_type.value,
        document_format=document_format.value,
    )
    save_order_pdf(relative_path=rel_path, pdf_bytes=pdf_bytes)

    doc = PDFDocument(
        company_id=order.company_id,
        service_order_id=order.id,
        generated_by_id=generated_by.id,
        document_type=document_type.value,
        document_format=document_format.value,
        file_url=rel_path,
        revision=revision,
        is_copy=is_copy,
    )
    db.add(doc)
    db.flush()
    return doc


def read_document_bytes(doc: PDFDocument) -> bytes:
    if doc.file_url.startswith("http://") or doc.file_url.startswith("https://"):
        raise FileNotFoundError("Documento remoto no soportado en Fase 1")
    return read_order_pdf(doc.file_url)


def auto_generate_intake_slips(db: Session, *, order: ServiceOrder, user: User) -> None:
    if not is_workshop_order_kind(order.order_kind):
        return
    for fmt in (OrderDocumentFormat.A4, OrderDocumentFormat.THERMAL):
        try:
            create_order_document(
                db,
                order=order,
                document_type=OrderDocumentType.WORKSHOP_INTAKE,
                document_format=fmt,
                generated_by=user,
            )
        except Exception:
            logger.exception("No se pudo generar comprobante de ingreso %s", fmt.value)


def auto_generate_delivery_slips(db: Session, *, order: ServiceOrder, user: User) -> None:
    for fmt in (OrderDocumentFormat.A4, OrderDocumentFormat.THERMAL):
        try:
            create_order_document(
                db,
                order=order,
                document_type=OrderDocumentType.DELIVERY_RECEIPT,
                document_format=fmt,
                generated_by=user,
            )
        except Exception:
            logger.exception("No se pudo generar comprobante de salida %s", fmt.value)
