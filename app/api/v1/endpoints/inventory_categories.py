from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.permissions import INVENTORY_READ, INVENTORY_WRITE
from app.db.models.inventory_category import InventoryCategory
from app.db.models.user import User
from app.db.session import get_db
from app.dependencies import RequirePermission, ensure_not_viewer_for_mutation
from app.schemas.inventory import (
    InventoryCategoryCreate,
    InventoryCategoryResponse,
    InventoryCategoryUpdate,
)

router = APIRouter(prefix="/inventory/categories", tags=["inventory-categories"])


@router.get("/", response_model=list[InventoryCategoryResponse])
def list_categories(
    current_user: User = Depends(RequirePermission(INVENTORY_READ)),
    db: Session = Depends(get_db),
) -> list[InventoryCategory]:
    return (
        db.query(InventoryCategory)
        .filter(InventoryCategory.company_id == current_user.company_id)
        .order_by(InventoryCategory.name)
        .all()
    )


@router.post("/", response_model=InventoryCategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: InventoryCategoryCreate,
    current_user: User = Depends(RequirePermission(INVENTORY_WRITE)),
    db: Session = Depends(get_db),
) -> InventoryCategory:
    ensure_not_viewer_for_mutation(current_user)

    exists = (
        db.query(InventoryCategory)
        .filter(
            InventoryCategory.company_id == current_user.company_id,
            InventoryCategory.name.ilike(payload.name),
        )
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="Ya existe una categoría con ese nombre")

    category = InventoryCategory(
        company_id=current_user.company_id,
        name=payload.name,
        color=payload.color or "#3b82f6",
        description=payload.description,
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.put("/{category_id}", response_model=InventoryCategoryResponse)
def update_category(
    category_id: UUID,
    payload: InventoryCategoryUpdate,
    current_user: User = Depends(RequirePermission(INVENTORY_WRITE)),
    db: Session = Depends(get_db),
) -> InventoryCategory:
    ensure_not_viewer_for_mutation(current_user)

    category = (
        db.query(InventoryCategory)
        .filter(
            InventoryCategory.id == category_id,
            InventoryCategory.company_id == current_user.company_id,
        )
        .first()
    )
    if not category:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")

    data = payload.model_dump(exclude_unset=True)
    if data.get("name") and data["name"].lower() != category.name.lower():
        exists = (
            db.query(InventoryCategory)
            .filter(
                InventoryCategory.company_id == current_user.company_id,
                InventoryCategory.name.ilike(data["name"]),
                InventoryCategory.id != category_id,
            )
            .first()
        )
        if exists:
            raise HTTPException(status_code=400, detail="Ya existe una categoría con ese nombre")

    for k, v in data.items():
        setattr(category, k, v)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: UUID,
    current_user: User = Depends(RequirePermission(INVENTORY_WRITE)),
    db: Session = Depends(get_db),
) -> None:
    ensure_not_viewer_for_mutation(current_user)

    category = (
        db.query(InventoryCategory)
        .filter(
            InventoryCategory.id == category_id,
            InventoryCategory.company_id == current_user.company_id,
        )
        .first()
    )
    if not category:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")

    db.delete(category)
    db.commit()
