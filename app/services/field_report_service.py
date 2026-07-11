from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.enums import FieldReportStatus
from app.db.models.field_report import FieldReport


def create_field_report(
    db: Session,
    *,
    company_id: UUID,
    technician_id: UUID,
    title: str,
    site_id: Optional[UUID] = None,
    order_id: Optional[UUID] = None,
    findings: Optional[str] = None,
    recommendations: Optional[str] = None,
    status: FieldReportStatus = FieldReportStatus.DRAFT,
    photos_urls: Optional[list[str]] = None,
) -> FieldReport:
    report = FieldReport(
        company_id=company_id,
        technician_id=technician_id,
        site_id=site_id,
        order_id=order_id,
        title=title,
        findings=findings,
        recommendations=recommendations,
        status=status,
        photos_urls=photos_urls or [],
    )
    db.add(report)
    db.flush()
    return report


def update_field_report(db: Session, report: FieldReport, data: dict) -> FieldReport:
    for key, value in data.items():
        if hasattr(report, key):
            setattr(report, key, value)
    db.flush()
    return report


def delete_field_report(db: Session, report: FieldReport) -> None:
    db.delete(report)
    db.flush()
