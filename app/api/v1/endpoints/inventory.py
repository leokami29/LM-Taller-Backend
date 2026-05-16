from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.exceptions import InsufficientStockError
from app.core.permissions import (
    INVENTORY_DELETE,
    INVENTORY_READ,
    INVENTORY_STOCK,
    INVENTORY_WRITE,
)
from app.dependencies import RequirePermission, ensure_not_viewer_for_mutation
from app.db.models.inventory import InventoryItem, InventoryMovement
from app.db.models.service_order import ServiceOrder
from app.db.models.supplier import Supplier
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.common import PaginatedResponse
from app.schemas.inventory import (
    InventoryItemCreate,
    InventoryItemResponse,
    InventoryItemUpdate,
    InventoryMovementResponse,
    InventoryStockChange,
)
from app.services.inventory_service import apply_stock_change

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("/", response_model=PaginatedResponse[InventoryItemResponse])
def list_inventory(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    current_user: User = Depends(RequirePermission(INVENTORY_READ)),
    db: Session = Depends(get_db),
) -> dict:
    q = db.query(InventoryItem).filter(InventoryItem.company_id == current_user.company_id)
    if search:
        term = f"%{search.lower()}%"
        q = q.filter(or_(InventoryItem.sku.ilike(term), InventoryItem.name.ilike(term)))
    if category:
        q = q.filter(InventoryItem.category.ilike(f"%{category}%"))
    total = q.count()
    items = q.order_by(InventoryItem.name).offset(skip).limit(limit).all()
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.post("/", response_model=InventoryItemResponse, status_code=status.HTTP_201_CREATED)
def create_inventory_item(
    payload: InventoryItemCreate,
    current_user: User = Depends(RequirePermission(INVENTORY_WRITE)),
    db: Session = Depends(get_db),
) -> InventoryItem:
    ensure_not_viewer_for_mutation(current_user)

    exists = (
        db.query(InventoryItem)
        .filter(
            InventoryItem.company_id == current_user.company_id,
            InventoryItem.sku == payload.sku,
        )
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="SKU duplicado en la empresa")

    if payload.supplier_id:
        sup = (
            db.query(Supplier)
            .filter(
                Supplier.id == payload.supplier_id,
                Supplier.company_id == current_user.company_id,
            )
            .first()
        )
        if not sup:
            raise HTTPException(status_code=400, detail="Proveedor no válido")

    item = InventoryItem(company_id=current_user.company_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/{item_id}", response_model=InventoryItemResponse)
def get_inventory_item(
    item_id: UUID,
    current_user: User = Depends(RequirePermission(INVENTORY_READ)),
    db: Session = Depends(get_db),
) -> InventoryItem:
    item = (
        db.query(InventoryItem)
        .filter(InventoryItem.id == item_id, InventoryItem.company_id == current_user.company_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Ítem no encontrado")
    return item


@router.put("/{item_id}", response_model=InventoryItemResponse)
def update_inventory_item(
    item_id: UUID,
    payload: InventoryItemUpdate,
    current_user: User = Depends(RequirePermission(INVENTORY_WRITE)),
    db: Session = Depends(get_db),
) -> InventoryItem:
    ensure_not_viewer_for_mutation(current_user)

    item = (
        db.query(InventoryItem)
        .filter(InventoryItem.id == item_id, InventoryItem.company_id == current_user.company_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Ítem no encontrado")

    data = payload.model_dump(exclude_unset=True)
    if data.get("sku") and data["sku"] != item.sku:
        exists = (
            db.query(InventoryItem)
            .filter(
                InventoryItem.company_id == current_user.company_id,
                InventoryItem.sku == data["sku"],
                InventoryItem.id != item_id,
            )
            .first()
        )
        if exists:
            raise HTTPException(status_code=400, detail="SKU duplicado en la empresa")
    if data.get("supplier_id"):
        sup = (
            db.query(Supplier)
            .filter(
                Supplier.id == data["supplier_id"],
                Supplier.company_id == current_user.company_id,
            )
            .first()
        )
        if not sup:
            raise HTTPException(status_code=400, detail="Proveedor no válido")

    for k, v in data.items():
        setattr(item, k, v)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}")
def delete_inventory_item(
    item_id: UUID,
    current_user: User = Depends(RequirePermission(INVENTORY_DELETE)),
    db: Session = Depends(get_db),
) -> dict:
    item = (
        db.query(InventoryItem)
        .filter(InventoryItem.id == item_id, InventoryItem.company_id == current_user.company_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Ítem no encontrado")
    db.delete(item)
    db.commit()
    return {"message": "Ítem eliminado", "status": "success"}


@router.post("/{item_id}/stock", response_model=InventoryMovementResponse)
def adjust_stock(
    item_id: UUID,
    payload: InventoryStockChange,
    db: Session = Depends(get_db),
    user: User = Depends(RequirePermission(INVENTORY_STOCK)),
) -> InventoryMovement:
    item = (
        db.query(InventoryItem)
        .filter(InventoryItem.id == item_id, InventoryItem.company_id == user.company_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Ítem no encontrado")

    if payload.service_order_id:
        so = (
            db.query(ServiceOrder)
            .filter(
                ServiceOrder.id == payload.service_order_id,
                ServiceOrder.company_id == user.company_id,
            )
            .first()
        )
        if not so:
            raise HTTPException(status_code=400, detail="Orden de servicio no válida")

    try:
        movement = apply_stock_change(
            db,
            item=item,
            company_id=user.company_id,
            movement_type=payload.movement_type,
            quantity_change=payload.quantity_change,
            moved_by_id=user.id,
            service_order_id=payload.service_order_id,
            notes=payload.notes,
        )
        db.commit()
        db.refresh(movement)
        return movement
    except InsufficientStockError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=e.message) from e
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e

@router.get("/movements", response_model=list[InventoryMovementResponse])
def get_all_inventory_movements(
    current_user: User = Depends(RequirePermission(INVENTORY_READ)),
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1),
) -> list[InventoryMovement]:
    movements = (
        db.query(InventoryMovement)
        .join(InventoryItem, InventoryItem.id == InventoryMovement.inventory_item_id)
        .filter(InventoryItem.company_id == current_user.company_id)
        .order_by(InventoryMovement.moved_at.desc())
        .limit(limit)
        .all()
    )
    return movements


@router.get("/{item_id}/movements", response_model=list[InventoryMovementResponse])
def get_inventory_movements(
    item_id: UUID,
    current_user: User = Depends(RequirePermission(INVENTORY_READ)),
    db: Session = Depends(get_db),
) -> list[InventoryMovement]:
    item = (
        db.query(InventoryItem)
        .filter(InventoryItem.id == item_id, InventoryItem.company_id == current_user.company_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Ítem no encontrado")

    movements = (
        db.query(InventoryMovement)
        .filter(InventoryMovement.inventory_item_id == item_id)
        .order_by(InventoryMovement.moved_at.desc())
        .all()
    )
    return movements

