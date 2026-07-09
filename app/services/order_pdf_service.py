from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

if TYPE_CHECKING:
    from app.db.models.service_order import ServiceOrder


def generate_order_pdf(order: ServiceOrder) -> bytes:
    """Genera un PDF de la orden de servicio."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=18,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=18,
        spaceAfter=12,
        textColor=colors.HexColor("#1a1a2e"),
    )
    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=14,
        spaceAfter=8,
        textColor=colors.HexColor("#16213e"),
    )
    normal_style = styles["BodyText"]
    normal_style.fontSize = 10

    elements = []

    # Header
    elements.append(Paragraph(f"Orden de Servicio #{order.order_number}", title_style))
    elements.append(Paragraph(f"Fecha: {order.created_at.strftime('%d/%m/%Y %H:%M')}", normal_style))
    elements.append(Spacer(1, 0.2 * inch))

    # Customer info
    elements.append(Paragraph("Cliente", heading_style))
    customer = order.current_customer
    customer_data = [
        ["Nombre", f"{customer.first_name} {customer.last_name}" if customer else "N/A"],
        ["Teléfono", customer.phone or "N/A" if customer else "N/A"],
        ["Email", customer.email or "N/A" if customer else "N/A"],
    ]
    customer_table = Table(customer_data, colWidths=[1.5 * inch, 4 * inch])
    customer_table.setStyle(
        TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ])
    )
    elements.append(customer_table)
    elements.append(Spacer(1, 0.2 * inch))

    # Equipment info
    elements.append(Paragraph("Equipo", heading_style))
    equipment = order.equipment
    equip_data = [
        ["Tipo", equipment.equipment_type or "N/A" if equipment else "N/A"],
        ["Marca", equipment.brand or "N/A" if equipment else "N/A"],
        ["Modelo", equipment.model or "N/A" if equipment else "N/A"],
        ["Serial", equipment.serial_number or "N/A" if equipment else "N/A"],
    ]
    equip_table = Table(equip_data, colWidths=[1.5 * inch, 4 * inch])
    equip_table.setStyle(
        TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ])
    )
    elements.append(equip_table)
    elements.append(Spacer(1, 0.2 * inch))

    # Order details
    elements.append(Paragraph("Detalles de la Orden", heading_style))
    details_data = [
        ["Estado", order.status.value if order.status else "N/A"],
        ["Prioridad", order.priority.value if order.priority else "N/A"],
        ["Problema reportado", order.problem_description or "N/A"],
        ["Diagnóstico", order.diagnosis_notes or "Pendiente"],
    ]
    details_table = Table(details_data, colWidths=[1.5 * inch, 4 * inch])
    details_table.setStyle(
        TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ])
    )
    elements.append(details_table)
    elements.append(Spacer(1, 0.2 * inch))

    # Cost lines
    elements.append(Paragraph("Costos", heading_style))
    if order.cost_lines:
        cost_data = [["Categoría", "Descripción", "Monto"]]
        for line in order.cost_lines:
            cost_data.append([
                line.category.value if line.category else "",
                line.description or "",
                f"${float(line.amount):,.2f}",
            ])
        cost_data.append(["", "Total", f"${float(order.total_cost):,.2f}"])
        cost_table = Table(cost_data, colWidths=[1.5 * inch, 3 * inch, 1 * inch])
        cost_table.setStyle(
            TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16213e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                ("BACKGROUND", (0, -1), (-1, -1), colors.lightgrey),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ])
        )
        elements.append(cost_table)
    else:
        elements.append(Paragraph("No hay líneas de costo registradas.", normal_style))
    elements.append(Spacer(1, 0.2 * inch))

    # Timeline
    elements.append(Paragraph("Historial", heading_style))
    if order.timeline_entries:
        timeline_data = [["Fecha", "Estado", "Notas"]]
        for entry in order.timeline_entries:
            timeline_data.append([
                entry.changed_at.strftime("%d/%m/%Y %H:%M"),
                entry.new_status,
                entry.notes or "",
            ])
        timeline_table = Table(timeline_data, colWidths=[1.5 * inch, 1.5 * inch, 3 * inch])
        timeline_table.setStyle(
            TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16213e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
            ])
        )
        elements.append(timeline_table)
    else:
        elements.append(Paragraph("No hay registros de historial.", normal_style))

    # Footer
    elements.append(Spacer(1, 0.3 * inch))
    elements.append(Paragraph("— Generado por SGtaller —", normal_style))

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
