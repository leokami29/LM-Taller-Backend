"""Comprobantes PDF de ingreso y salida con logo, código de barras Code128 y QR."""

from __future__ import annotations

import base64
import logging
import urllib.request
from datetime import datetime
from io import BytesIO
from typing import TYPE_CHECKING, Literal

import barcode
import qrcode
from barcode.writer import ImageWriter
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.enums import OrderDocumentFormat, OrderDocumentType
from app.services.order_pdf_service import generate_order_pdf

if TYPE_CHECKING:
    from app.db.models.service_order import ServiceOrder

logger = logging.getLogger(__name__)

DocumentFormat = Literal["a4", "thermal"]

THERMAL_WIDTH = 80 * mm
THERMAL_HEIGHT = 297 * mm

BRAND_DARK = colors.HexColor("#1a1a2e")
BRAND_MID = colors.HexColor("#16213e")
HEADER_BG = colors.HexColor("#f0f4fa")
BORDER_GREY = colors.HexColor("#cccccc")


# ─── Barcode + QR ────────────────────────────────────────────────────────────

def render_barcode_image(tracking_code: str) -> bytes:
    code = barcode.get("code128", tracking_code, writer=ImageWriter())
    buf = BytesIO()
    code.write(buf, options={"module_height": 8, "font_size": 8, "text_distance": 2})
    buf.seek(0)
    return buf.getvalue()


def render_qr_image(data: str, size_px: int = 120) -> bytes:
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=4, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


# ─── Logo ─────────────────────────────────────────────────────────────────────

def _load_logo(company) -> ImageReader | None:
    if not company:
        return None
    logo_url: str | None = getattr(company, "logo_url", None)
    if not logo_url:
        return None
    try:
        if logo_url.startswith("data:"):
            # data URI base64
            header, encoded = logo_url.split(",", 1)
            img_bytes = base64.b64decode(encoded)
            return ImageReader(BytesIO(img_bytes))
        else:
            req = urllib.request.Request(logo_url, headers={"User-Agent": "SGtaller/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                return ImageReader(BytesIO(resp.read()))
    except Exception:
        logger.debug("No se pudo cargar logo desde %s", logo_url)
        return None


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _fmt_dt(dt: datetime | None) -> str:
    return dt.strftime("%d/%m/%Y %H:%M") if dt else "—"


def _customer_name(order: ServiceOrder) -> str:
    c = order.current_customer
    return f"{c.first_name} {c.last_name}".strip() if c else "N/A"


def _company_info(order: ServiceOrder) -> dict:
    """Devuelve info de empresa/sede con prioridad: sede → empresa."""
    company = order.company
    site = order.site
    name = company.name if company else "Taller"
    address = (getattr(site, "address_override", None) or None) if site else None
    if not address:
        address = company.address if company else ""
    phone = (getattr(site, "phone", None) or None) if site else None
    if not phone:
        phone = company.phone if company else None
    email = (getattr(site, "email", None) or None) if site else None
    if not email:
        email = company.email if company else None
    site_name = site.name if site else None
    return {
        "name": name,
        "site_name": site_name,
        "address": address or "",
        "phone": phone or "",
        "email": email or "",
    }


def _receptionist_name(order: ServiceOrder) -> str:
    user = order.received_by
    return user.full_name if user and user.full_name else "—"


def _assigned_tech_name(order: ServiceOrder) -> str:
    user = order.assigned_technician
    return user.full_name if user and user.full_name else "—"


def _equipment_rows(order: ServiceOrder) -> list[list[str]]:
    eq = order.equipment
    if not eq:
        return [["Equipo", "N/A"]]
    rows = [
        ["Tipo", eq.equipment_type or "—"],
        ["Marca / Modelo", f"{eq.brand or '—'} / {eq.model or '—'}"],
        ["Serial", eq.serial_number or "—"],
    ]
    if getattr(eq, "imei", None):
        rows.append(["IMEI", eq.imei])
    if getattr(eq, "barcode", None):
        rows.append(["Cód. equipo", eq.barcode])
    return rows


def _barcode_flowable(tracking: str, *, width: float, height: float) -> Image | None:
    try:
        return Image(BytesIO(render_barcode_image(tracking)), width=width, height=height)
    except Exception:
        logger.exception("No se pudo generar código de barras para %s", tracking)
        return None


def _qr_flowable(tracking: str, *, size: float) -> Image | None:
    try:
        return Image(BytesIO(render_qr_image(tracking)), width=size, height=size)
    except Exception:
        logger.exception("No se pudo generar QR para %s", tracking)
        return None


def _accessories_text(order: ServiceOrder) -> str | None:
    acc: dict | None = getattr(order, "accessories_json", None)
    if not acc:
        return None
    parts = []
    checks = [("cables", "Cables"), ("charger", "Cargador"), ("case", "Funda")]
    for key, label in checks:
        if acc.get(key):
            parts.append(f"☑ {label}")
        else:
            parts.append(f"☐ {label}")
    if acc.get("battery_pct") is not None:
        parts.append(f"Batería: {acc['battery_pct']}%")
    if acc.get("scratches"):
        parts.append(f"Rayones: {acc['scratches']}")
    return "   ".join(parts) if parts else None


# ─── Copy watermark ───────────────────────────────────────────────────────────

def _make_copy_watermark(revision: int):
    def on_page(canvas_obj, doc):
        if revision <= 1:
            return
        canvas_obj.saveState()
        canvas_obj.setFont("Helvetica-Bold", 60)
        canvas_obj.setFillColorRGB(0.8, 0.8, 0.8, alpha=0.3)
        canvas_obj.translate(doc.width / 2 + doc.leftMargin, doc.height / 2 + doc.bottomMargin)
        canvas_obj.rotate(40)
        canvas_obj.drawCentredString(0, 0, f"COPIA #{revision}")
        canvas_obj.restoreState()
    return on_page


# ─── Styles ──────────────────────────────────────────────────────────────────

def _styles(font_body: int):
    styles = getSampleStyleSheet()
    title_s = ParagraphStyle("DocTitle", parent=styles["Heading1"], fontSize=font_body + 4, spaceAfter=2, textColor=BRAND_DARK)
    sub_s = ParagraphStyle("DocSub", parent=styles["BodyText"], fontSize=font_body - 1, spaceAfter=2, textColor=BRAND_MID)
    normal_s = ParagraphStyle("DocNormal", parent=styles["BodyText"], fontSize=font_body, spaceAfter=2)
    label_s = ParagraphStyle("DocLabel", parent=styles["BodyText"], fontSize=font_body - 1, textColor=colors.grey)
    return title_s, sub_s, normal_s, label_s


def _table_style(header_bg=HEADER_BG):
    return TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER_GREY),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (0, -1), header_bg),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ])


# ─── Main builder ────────────────────────────────────────────────────────────

def _build_pdf(
    order: ServiceOrder,
    *,
    title: str,
    subtitle: str,
    extra_rows: list[list[str]],
    format: DocumentFormat,
    include_signatures: bool,
    revision: int = 1,
) -> bytes:
    buffer = BytesIO()
    if format == OrderDocumentFormat.THERMAL.value:
        pagesize = (THERMAL_WIDTH, THERMAL_HEIGHT)
        lm = rm = tm = bm = 4 * mm
        font_body = 8
        label_w = 22 * mm
        val_w = THERMAL_WIDTH - label_w - 8 * mm
    else:
        pagesize = A4
        lm = rm = 15 * mm
        tm = bm = 15 * mm
        font_body = 10
        label_w = 42 * mm
        val_w = A4[0] - label_w - lm - rm - 4 * mm

    is_copy = revision > 1
    watermark_fn = _make_copy_watermark(revision) if is_copy else None

    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=lm,
        rightMargin=rm,
        topMargin=tm,
        bottomMargin=bm,
        onFirstPage=watermark_fn or (lambda c, d: None),
        onLaterPages=watermark_fn or (lambda c, d: None),
    )

    title_s, sub_s, normal_s, label_s = _styles(font_body)
    elements = []

    # ── Header ─────────────────────────────────────────────────────────────────
    info = _company_info(order)
    logo_reader = _load_logo(order.company)
    tracking = order.tracking_code or ""

    if format == OrderDocumentFormat.THERMAL.value:
        # Térmico: centrado
        if logo_reader:
            elements.append(Image(logo_reader, width=20 * mm, height=20 * mm, hAlign="CENTER"))
            elements.append(Spacer(1, 1 * mm))
        elements.append(Paragraph(f"<b>{info['name']}</b>", title_s))
        if info["site_name"]:
            elements.append(Paragraph(info["site_name"], sub_s))
        if info["address"]:
            elements.append(Paragraph(info["address"], label_s))
        if info["phone"]:
            elements.append(Paragraph(f"Tel: {info['phone']}", label_s))
        if info["email"]:
            elements.append(Paragraph(info["email"], label_s))
        elements.append(Spacer(1, 2 * mm))
        elements.append(Paragraph(f"<b>{title}</b>", title_s))
        elements.append(Paragraph(f"Orden: <b>{order.order_number}</b>", normal_s))
        if tracking:
            bc_img = _barcode_flowable(tracking, width=val_w * 0.95, height=10 * mm)
            if bc_img:
                elements.append(bc_img)
            qr_img = _qr_flowable(tracking, size=18 * mm)
            if qr_img:
                elements.append(qr_img)
            elements.append(Paragraph(tracking, label_s))
    else:
        # A4: 3 columnas: logo | empresa | orden+barcode
        logo_cell = ""
        if logo_reader:
            logo_cell = Image(logo_reader, width=30 * mm, height=30 * mm)

        company_text = f"<b>{info['name']}</b>"
        if info["site_name"]:
            company_text += f"<br/>{info['site_name']}"
        if info["address"]:
            company_text += f"<br/><font size='8'>{info['address']}</font>"
        if info["phone"]:
            company_text += f"<br/><font size='8'>Tel: {info['phone']}</font>"
        if info["email"]:
            company_text += f"<br/><font size='8'>{info['email']}</font>"
        company_para = Paragraph(company_text, normal_s)

        order_text = f"<b><font size='13'>{title}</font></b><br/>Orden: <b>{order.order_number}</b>"
        if is_copy:
            order_text += f"<br/><font color='red' size='8'>COPIA #{revision}</font>"
        order_para = Paragraph(order_text, normal_s)

        total_w = A4[0] - lm - rm
        logo_col_w = 32 * mm
        company_col_w = total_w * 0.45
        order_col_w = total_w - logo_col_w - company_col_w

        header_data = [[logo_cell, company_para, order_para]]
        header_table = Table(header_data, colWidths=[logo_col_w, company_col_w, order_col_w])
        header_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER_GREY),
            ("BACKGROUND", (0, 0), (-1, -1), HEADER_BG),
        ]))
        elements.append(header_table)

        if tracking:
            bc_img = _barcode_flowable(tracking, width=total_w * 0.68, height=12 * mm)
            qr_img = _qr_flowable(tracking, size=24 * mm)
            scan_cells: list = []
            if bc_img:
                scan_cells.append(bc_img)
            if qr_img:
                scan_cells.append(qr_img)
            if scan_cells:
                elements.append(Spacer(1, 2 * mm))
                if len(scan_cells) == 2:
                    scan_table = Table(
                        [scan_cells],
                        colWidths=[total_w * 0.72, total_w * 0.28],
                    )
                    scan_table.setStyle(TableStyle([
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (0, 0), (0, 0), "CENTER"),
                        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ]))
                    elements.append(scan_table)
                else:
                    elements.append(scan_cells[0])
                elements.append(
                    Paragraph(
                        f"<para align='center'><font size='9'><b>{tracking}</b></font></para>",
                        label_s,
                    )
                )

    elements.append(Spacer(1, 3 * mm))

    # ── Fecha ingreso + cliente ────────────────────────────────────────────────
    reception_info = [
        ["Fecha ingreso", _fmt_dt(order.received_at)],
        ["Recepcionó", _receptionist_name(order)],
    ] + extra_rows

    customer = order.current_customer
    client_info = [
        ["Cliente", _customer_name(order)],
        ["Teléfono", (customer.phone if customer else None) or "—"],
        ["Email", (customer.email if customer else None) or "—"],
    ]
    if customer and getattr(customer, "address", None):
        client_info.append(["Dirección", customer.address])

    if format == OrderDocumentFormat.A4.value:
        total_w = A4[0] - lm - rm
        left_w = total_w * 0.44
        right_w = total_w - left_w - 2 * mm
        left_t = Table([[Paragraph("<b>Recepción</b>", sub_s)]] + reception_info, colWidths=[label_w * 0.7, left_w - label_w * 0.7])
        left_t.setStyle(_table_style())
        right_t = Table([[Paragraph("<b>Cliente</b>", sub_s)]] + client_info, colWidths=[label_w * 0.7, right_w - label_w * 0.7])
        right_t.setStyle(_table_style())
        two_col = Table([[left_t, right_t]], colWidths=[left_w, right_w])
        two_col.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        elements.append(two_col)
    else:
        elements.append(Paragraph("<b>Recepción</b>", sub_s))
        elements.append(Table(reception_info, colWidths=[label_w, val_w]))
        elements[-1].setStyle(_table_style())
        elements.append(Spacer(1, 2 * mm))
        elements.append(Paragraph("<b>Cliente</b>", sub_s))
        elements.append(Table(client_info, colWidths=[label_w, val_w]))
        elements[-1].setStyle(_table_style())

    elements.append(Spacer(1, 2 * mm))

    # ── Equipo ────────────────────────────────────────────────────────────────
    elements.append(Paragraph("<b>Equipo</b>", sub_s))
    eq_t = Table(_equipment_rows(order), colWidths=[label_w, val_w if format == "thermal" else A4[0] - lm - rm - label_w])
    eq_t.setStyle(_table_style())
    elements.append(eq_t)
    elements.append(Spacer(1, 2 * mm))

    # ── Falla ─────────────────────────────────────────────────────────────────
    elements.append(Paragraph("<b>Falla reportada</b>", sub_s))
    elements.append(Paragraph(order.problem_description or "—", normal_s))

    if order.device_condition_on_entry:
        elements.append(Spacer(1, 1 * mm))
        elements.append(Paragraph("<b>Condición al ingreso</b>", sub_s))
        elements.append(Paragraph(order.device_condition_on_entry, normal_s))

    # ── Accesorios ────────────────────────────────────────────────────────────
    acc_text = _accessories_text(order)
    if acc_text:
        elements.append(Spacer(1, 1 * mm))
        elements.append(Paragraph("<b>Accesorios recibidos</b>", sub_s))
        elements.append(Paragraph(acc_text, normal_s))

    elements.append(Spacer(1, 2 * mm))

    # ── Técnico + fecha prometida ──────────────────────────────────────────────
    tech_rows = [
        ["Técnico asignado", _assigned_tech_name(order)],
        ["Fecha prometida", _fmt_dt(order.estimated_completion)],
    ]
    tech_t = Table(tech_rows, colWidths=[label_w, val_w if format == "thermal" else A4[0] - lm - rm - label_w])
    tech_t.setStyle(_table_style())
    elements.append(tech_t)

    # ── Firmas ────────────────────────────────────────────────────────────────
    if include_signatures and format == OrderDocumentFormat.A4.value:
        elements.append(Spacer(1, 10 * mm))
        total_w = A4[0] - lm - rm
        sig_t = Table(
            [["Firma cliente:", "_________________________", "Firma taller:", "_________________________"]],
            colWidths=[total_w * 0.22, total_w * 0.28, total_w * 0.22, total_w * 0.28],
        )
        sig_t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 16),
        ]))
        elements.append(sig_t)

    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph(f"<font size='7' color='grey'>— SGtaller — {datetime.now().strftime('%d/%m/%Y %H:%M')} —</font>", normal_s))

    doc.build(elements)
    data = buffer.getvalue()
    buffer.close()
    return data


# ─── Public API ──────────────────────────────────────────────────────────────

def generate_intake_slip(order: ServiceOrder, format: DocumentFormat = "a4", revision: int = 1) -> bytes:
    return _build_pdf(
        order,
        title="Comprobante de ingreso",
        subtitle="Orden de ingreso a taller",
        extra_rows=[],
        format=format,
        include_signatures=True,
        revision=revision,
    )


def generate_delivery_slip(order: ServiceOrder, format: DocumentFormat = "a4", revision: int = 1) -> bytes:
    delivery_dt = order.actual_completion
    if not delivery_dt and order.timeline_entries:
        for entry in sorted(order.timeline_entries, key=lambda e: e.changed_at, reverse=True):
            if entry.new_status == "delivered":
                delivery_dt = entry.changed_at
                break
    extra = [
        ["Fecha entrega", _fmt_dt(delivery_dt)],
        ["Total", f"${float(order.total_cost):,.2f}"],
        ["Estado", order.status.value if order.status else "—"],
    ]
    if order.diagnosis_notes:
        extra.append(["Diagnóstico", order.diagnosis_notes[:200]])
    return _build_pdf(
        order,
        title="Comprobante de salida",
        subtitle="Orden de entrega",
        extra_rows=extra,
        format=format,
        include_signatures=True,
        revision=revision,
    )


def generate_document_pdf(
    order: ServiceOrder,
    *,
    document_type: OrderDocumentType,
    format: DocumentFormat,
    revision: int = 1,
) -> bytes:
    if document_type == OrderDocumentType.WORKSHOP_INTAKE:
        return generate_intake_slip(order, format=format, revision=revision)
    if document_type == OrderDocumentType.DELIVERY_RECEIPT:
        return generate_delivery_slip(order, format=format, revision=revision)
    if document_type == OrderDocumentType.WORK_ORDER_SUMMARY:
        if format == OrderDocumentFormat.THERMAL.value:
            return generate_intake_slip(order, format=format, revision=revision)
        return generate_order_pdf(order)
    raise ValueError(f"Tipo de documento no soportado: {document_type}")
