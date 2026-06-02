"""Servicio de email: envío de PDF a cliente vía SMTP configurado en la empresa."""
from __future__ import annotations

import logging
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

from app.schemas.company import CompanyEmailSettings

if TYPE_CHECKING:
    from app.db.models.service_order import ServiceOrder

logger = logging.getLogger(__name__)


def get_smtp_config(company) -> CompanyEmailSettings | None:
    raw = (company.settings_json or {}).get("email_settings") if company else None
    if not raw:
        return None
    return CompanyEmailSettings(**raw)


def send_pdf_to_client(
    *,
    order: ServiceOrder,
    pdf_bytes: bytes,
    doc_type: str,
    recipient_email: str,
    smtp_config: CompanyEmailSettings,
    filename: str | None = None,
) -> None:
    if not smtp_config.smtp_host:
        raise ValueError("SMTP no configurado en esta empresa")

    company_name = order.company.name if order.company else "SGtaller"
    from_email = smtp_config.smtp_from_email or smtp_config.smtp_user or ""
    from_name = smtp_config.smtp_from_name or company_name
    subject = _subject(doc_type, order.order_number)

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = recipient_email

    body_html = _body_html(order, doc_type, company_name)
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    pdf_filename = filename or f"{doc_type}-{order.order_number}.pdf"
    attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
    attachment.add_header("Content-Disposition", "attachment", filename=pdf_filename)
    msg.attach(attachment)

    port = smtp_config.smtp_port or 587
    with smtplib.SMTP(smtp_config.smtp_host, port, timeout=15) as server:
        if smtp_config.smtp_use_tls:
            server.starttls()
        if smtp_config.smtp_user and smtp_config.smtp_password:
            server.login(smtp_config.smtp_user, smtp_config.smtp_password)
        server.send_message(msg)
    logger.info("PDF %s enviado a %s para orden %s", doc_type, recipient_email, order.order_number)


def send_test_email(*, smtp_config: CompanyEmailSettings, recipient_email: str) -> None:
    if not smtp_config.smtp_host:
        raise ValueError("SMTP no configurado")
    from_email = smtp_config.smtp_from_email or smtp_config.smtp_user or ""
    from_name = smtp_config.smtp_from_name or "SGtaller"
    msg = MIMEText("Este es un email de prueba enviado desde SGtaller.", "plain", "utf-8")
    msg["Subject"] = "Prueba de email — SGtaller"
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = recipient_email
    port = smtp_config.smtp_port or 587
    with smtplib.SMTP(smtp_config.smtp_host, port, timeout=15) as server:
        if smtp_config.smtp_use_tls:
            server.starttls()
        if smtp_config.smtp_user and smtp_config.smtp_password:
            server.login(smtp_config.smtp_user, smtp_config.smtp_password)
        server.send_message(msg)


def _subject(doc_type: str, order_number: str) -> str:
    labels = {
        "workshop_intake": "Comprobante de ingreso",
        "delivery_receipt": "Comprobante de entrega",
        "work_order_summary": "Orden de servicio",
    }
    return f"{labels.get(doc_type, 'Documento')} — Orden {order_number}"


def _body_html(order, doc_type: str, company_name: str) -> str:
    customer_name = ""
    if order.current_customer:
        c = order.current_customer
        customer_name = f"{c.first_name} {c.last_name}".strip()
    return f"""
<html><body style="font-family:sans-serif;color:#333">
<h2 style="color:#1a1a2e">{company_name}</h2>
<p>Estimado/a <strong>{customer_name or 'cliente'}</strong>,</p>
<p>Adjuntamos el comprobante correspondiente a su orden de servicio
<strong>{order.order_number}</strong>.</p>
<p>Si tiene alguna consulta, no dude en contactarnos.</p>
<hr/><p style="font-size:12px;color:#888">{company_name} — Generado por SGtaller</p>
</body></html>
"""
