from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from typing import Optional
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.orm import Query, Session

from app.db.models.inventory import InventoryItem, InventoryMovement


@dataclass
class InventoryListFilters:
    search: str | None = None
    category: str | None = None


def _base_items_query(db: Session, company_id: UUID) -> Query:
    return db.query(InventoryItem).filter(InventoryItem.company_id == company_id)


def _apply_item_filters(q: Query, filters: InventoryListFilters) -> Query:
    if filters.search:
        term = f"%{filters.search.lower()}%"
        q = q.filter(
            or_(
                InventoryItem.sku.ilike(term),
                InventoryItem.name.ilike(term),
                InventoryItem.barcode.ilike(term),
            )
        )
    if filters.category:
        q = q.filter(InventoryItem.category.ilike(f"%{filters.category}%"))
    return q


def list_items(
    db: Session,
    *,
    company_id: UUID,
    skip: int,
    limit: int,
    filters: InventoryListFilters,
) -> tuple[list[InventoryItem], int]:
    q = _apply_item_filters(_base_items_query(db, company_id), filters)
    total = q.count()
    items = q.order_by(InventoryItem.name).offset(skip).limit(limit).all()
    return items, total


def list_low_stock(
    db: Session,
    *,
    company_id: UUID,
    skip: int,
    limit: int,
) -> tuple[list[InventoryItem], int]:
    q = db.query(InventoryItem).filter(
        InventoryItem.company_id == company_id,
        InventoryItem.quantity_stock <= InventoryItem.quantity_minimum,
    )
    total = q.count()
    items = q.order_by(InventoryItem.name).offset(skip).limit(limit).all()
    return items, total


def list_categories(db: Session, *, company_id: UUID) -> list[str]:
    rows = (
        db.query(InventoryItem.category)
        .filter(InventoryItem.company_id == company_id, InventoryItem.category.isnot(None))
        .distinct()
        .order_by(InventoryItem.category)
        .all()
    )
    return [r[0] for r in rows if r[0]]


def export_items_csv(
    db: Session,
    *,
    company_id: UUID,
    filters: InventoryListFilters,
) -> bytes:
    q = _apply_item_filters(_base_items_query(db, company_id), filters)
    items = q.order_by(InventoryItem.name).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "sku",
        "name",
        "category",
        "quantity_stock",
        "quantity_minimum",
        "unit_cost",
        "unit_price",
        "barcode",
        "supplier_id",
        "last_restocked_at",
        "created_at",
    ])
    for item in items:
        writer.writerow([
            item.sku,
            item.name,
            item.category or "",
            float(item.quantity_stock or 0),
            float(item.quantity_minimum or 0),
            float(item.unit_cost or 0),
            float(item.unit_price or 0),
            item.barcode or "",
            str(item.supplier_id) if item.supplier_id else "",
            item.last_restocked_at.isoformat() if item.last_restocked_at else "",
            item.created_at.isoformat() if item.created_at else "",
        ])
    csv_bytes = output.getvalue().encode("utf-8-sig")
    output.close()
    return csv_bytes


def inventory_analytics_summary(db: Session, *, company_id: UUID) -> dict:
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_items = db.query(InventoryItem).filter(InventoryItem.company_id == company_id).count()
    low_stock_count = (
        db.query(InventoryItem)
        .filter(
            InventoryItem.company_id == company_id,
            InventoryItem.quantity_stock <= InventoryItem.quantity_minimum,
        )
        .count()
    )
    total_value = (
        db.query(func.sum(InventoryItem.quantity_stock * InventoryItem.unit_cost))
        .filter(InventoryItem.company_id == company_id)
        .scalar()
    ) or 0
    movements_month = (
        db.query(InventoryMovement)
        .join(InventoryItem, InventoryItem.id == InventoryMovement.inventory_item_id)
        .filter(InventoryItem.company_id == company_id, InventoryMovement.moved_at >= month_start)
        .count()
    )
    movement_breakdown = {}
    for mtype in ["purchase", "used_in_repair", "sale", "adjustment", "damage"]:
        count = (
            db.query(InventoryMovement)
            .join(InventoryItem, InventoryItem.id == InventoryMovement.inventory_item_id)
            .filter(
                InventoryItem.company_id == company_id,
                InventoryMovement.movement_type == mtype,
                InventoryMovement.moved_at >= month_start,
            )
            .count()
        )
        movement_breakdown[mtype] = count

    return {
        "total_items": total_items,
        "low_stock_count": low_stock_count,
        "total_value": float(total_value),
        "movements_this_month": movements_month,
        "movement_breakdown": movement_breakdown,
    }


def get_item(db: Session, *, company_id: UUID, item_id: UUID) -> InventoryItem | None:
    return (
        db.query(InventoryItem)
        .filter(InventoryItem.id == item_id, InventoryItem.company_id == company_id)
        .first()
    )


def get_global_movements(db: Session, *, company_id: UUID, limit: int) -> list[InventoryMovement]:
    return (
        db.query(InventoryMovement)
        .join(InventoryItem, InventoryItem.id == InventoryMovement.inventory_item_id)
        .filter(InventoryItem.company_id == company_id)
        .order_by(InventoryMovement.moved_at.desc())
        .limit(limit)
        .all()
    )


def get_item_movements(
    db: Session,
    *,
    item_id: UUID,
    movement_type: Optional[str] = None,
) -> list[InventoryMovement]:
    q = db.query(InventoryMovement).filter(InventoryMovement.inventory_item_id == item_id)
    if movement_type:
        q = q.filter(InventoryMovement.movement_type == movement_type)
    return q.order_by(InventoryMovement.moved_at.desc()).all()
