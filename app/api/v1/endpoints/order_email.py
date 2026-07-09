"""Endpoint para enviar PDF de una orden por email al cliente."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.permissions import ORDERS_WRITE
from app.db.models.pdf_document import PDFDocument
from app.db.models.user import User
from app.db.session import get_db
from app.dependencies import RequirePermission
from app.services.email_service import get_smtp_config, send_pdf_to_client, send_test_email
from app.services.order_document_registry import load_order_for_documents, read_document_bytes

router = APIRouter(prefix="/orders", tags=["order-email"])


class SendEmailPayload(BaseModel):
    recipient_email: EmailStr


@router.post("/{order_id}/documents/{doc_id}/send-email")
def send_document_by_email(
    order_id: UUID,
    doc_id: UUID,
    payload: SendEmailPayload,
    current_user: User = Depends(RequirePermission(ORDERS_WRITE)),
    db: Session = Depends(get_db),
) -> dict:
    order = load_order_for_documents(db, company_id=current_user.company_id, order_id=order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    doc = (
        db.query(PDFDocument)
        .filter(
            PDFDocument.id == doc_id,
            PDFDocument.service_order_id == order_id,
            PDFDocument.company_id == current_user.company_id,
        )
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    smtp_config = get_smtp_config(order.company)
    if not smtp_config or not smtp_config.smtp_host:
        raise HTTPException(
            status_code=422,
            detail="Email no configurado. Configure SMTP en Ajustes → Perfil de empresa.",
        )

    try:
        pdf_bytes = read_document_bytes(doc)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Archivo PDF no encontrado")

    try:
        send_pdf_to_client(
            order=order,
            pdf_bytes=pdf_bytes,
            doc_type=doc.document_type,
            recipient_email=str(payload.recipient_email),
            smtp_config=smtp_config,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error al enviar email: {exc}") from exc

    return {"message": f"Email enviado a {payload.recipient_email}"}


class TestEmailPayload(BaseModel):
    recipient_email: EmailStr


@router.post("/email/test")
def test_smtp_email(
    payload: TestEmailPayload,
    current_user: User = Depends(RequirePermission(ORDERS_WRITE)),
    db: Session = Depends(get_db),
) -> dict:
    from app.db.models.company import Company
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    smtp_config = get_smtp_config(company)
    if not smtp_config or not smtp_config.smtp_host:
        raise HTTPException(status_code=422, detail="SMTP no configurado")
    try:
        send_test_email(smtp_config=smtp_config, recipient_email=str(payload.recipient_email))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error SMTP: {exc}") from exc
    return {"message": f"Email de prueba enviado a {payload.recipient_email}"}
