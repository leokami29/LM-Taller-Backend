from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.permissions import (
    EQUIPMENT_DELETE,
    EQUIPMENT_READ,
    EQUIPMENT_WRITE,
)
from app.dependencies import RequirePermission, ensure_not_viewer_for_mutation
from app.db.models.customer import Customer
from app.db.models.equipment import Equipment
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.common import PaginatedResponse
from app.schemas.equipment import EquipmentCreate, EquipmentResponse, EquipmentUpdate

router = APIRouter(prefix="/equipment", tags=["equipment"])


@router.get("/", response_model=PaginatedResponse[EquipmentResponse])
def list_equipment(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    current_user: User = Depends(RequirePermission(EQUIPMENT_READ)),
    db: Session = Depends(get_db),
) -> dict:
    q = db.query(Equipment).filter(Equipment.company_id == current_user.company_id)
    if search:
        term = f"%{search.lower()}%"
        q = q.filter(
            or_(
                Equipment.serial_number.ilike(term),
                Equipment.model.ilike(term),
                Equipment.brand.ilike(term),
            )
        )
    if brand:
        q = q.filter(Equipment.brand.ilike(f"%{brand}%"))
    total = q.count()
    items = q.order_by(Equipment.created_at.desc()).offset(skip).limit(limit).all()
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.post("/", response_model=EquipmentResponse, status_code=status.HTTP_201_CREATED)
def create_equipment(
    payload: EquipmentCreate,
    current_user: User = Depends(RequirePermission(EQUIPMENT_WRITE)),
    db: Session = Depends(get_db),
) -> Equipment:
    ensure_not_viewer_for_mutation(current_user)

    exists = (
        db.query(Equipment)
        .filter(
            Equipment.company_id == current_user.company_id,
            Equipment.serial_number == payload.serial_number,
        )
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="Serial duplicado en la empresa")

    if payload.original_owner_id:
        owner = (
            db.query(Customer)
            .filter(
                Customer.id == payload.original_owner_id,
                Customer.company_id == current_user.company_id,
            )
            .first()
        )
        if not owner:
            raise HTTPException(status_code=400, detail="Propietario original no válido")

    eq = Equipment(company_id=current_user.company_id, **payload.model_dump())
    if eq.first_received_date is None:
        eq.first_received_date = date.today()
    db.add(eq)
    db.commit()
    db.refresh(eq)
    return eq


@router.get("/{equipment_id}", response_model=EquipmentResponse)
def get_equipment(
    equipment_id: UUID,
    current_user: User = Depends(RequirePermission(EQUIPMENT_READ)),
    db: Session = Depends(get_db),
) -> Equipment:
    eq = (
        db.query(Equipment)
        .filter(Equipment.id == equipment_id, Equipment.company_id == current_user.company_id)
        .first()
    )
    if not eq:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    return eq


@router.put("/{equipment_id}", response_model=EquipmentResponse)
def update_equipment(
    equipment_id: UUID,
    payload: EquipmentUpdate,
    current_user: User = Depends(RequirePermission(EQUIPMENT_WRITE)),
    db: Session = Depends(get_db),
) -> Equipment:
    ensure_not_viewer_for_mutation(current_user)

    eq = (
        db.query(Equipment)
        .filter(Equipment.id == equipment_id, Equipment.company_id == current_user.company_id)
        .first()
    )
    if not eq:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")

    data = payload.model_dump(exclude_unset=True)
    new_serial = data.get("serial_number")
    if new_serial and new_serial != eq.serial_number:
        exists = (
            db.query(Equipment)
            .filter(
                Equipment.company_id == current_user.company_id,
                Equipment.serial_number == new_serial,
                Equipment.id != equipment_id,
            )
            .first()
        )
        if exists:
            raise HTTPException(status_code=400, detail="Serial duplicado en la empresa")

    if data.get("original_owner_id"):
        owner = (
            db.query(Customer)
            .filter(
                Customer.id == data["original_owner_id"],
                Customer.company_id == current_user.company_id,
            )
            .first()
        )
        if not owner:
            raise HTTPException(status_code=400, detail="Propietario original no válido")

    for k, v in data.items():
        setattr(eq, k, v)
    db.add(eq)
    db.commit()
    db.refresh(eq)
    return eq


@router.delete("/{equipment_id}")
def delete_equipment(
    equipment_id: UUID,
    current_user: User = Depends(RequirePermission(EQUIPMENT_DELETE)),
    db: Session = Depends(get_db),
) -> dict:
    eq = (
        db.query(Equipment)
        .filter(Equipment.id == equipment_id, Equipment.company_id == current_user.company_id)
        .first()
    )
    if not eq:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    db.delete(eq)
    db.commit()
    return {"message": "Equipo eliminado", "status": "success"}
