from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.permissions import (
    EQUIPMENT_DELETE,
    EQUIPMENT_READ,
    EQUIPMENT_WRITE,
)
from app.db.models.customer import Customer
from app.db.models.equipment import Equipment, EquipmentAttribute
from app.db.models.user import User
from app.db.session import get_db
from app.dependencies import RequirePermission, ensure_not_viewer_for_mutation
from app.schemas.common import PaginatedResponse
from app.schemas.equipment import (
    EquipmentAttributeCreate,
    EquipmentAttributeResponse,
    EquipmentAttributeUpdate,
    EquipmentCreate,
    EquipmentResponse,
    EquipmentUpdate,
)
from app.utils.helpers import apply_allowed_updates

router = APIRouter(prefix="/equipment", tags=["equipment"])

_EQUIPMENT_LOAD_OPTS = [
    joinedload(Equipment.original_owner),
    joinedload(Equipment.attributes),
]


def _load_equipment(db: Session, company_id: UUID, equipment_id: UUID) -> Equipment | None:
    return (
        db.query(Equipment)
        .options(*_EQUIPMENT_LOAD_OPTS)
        .filter(Equipment.id == equipment_id, Equipment.company_id == company_id)
        .first()
    )


@router.get("/", response_model=PaginatedResponse[EquipmentResponse])
def list_equipment(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    owner_id: Optional[UUID] = Query(None, description="Filtrar equipos por propietario (cliente)"),
    category: Optional[str] = Query(None, description="Filtrar por categoría"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filtrar por estado"),
    barcode: Optional[str] = Query(None, description="Buscar por código de barras exacto"),
    current_user: User = Depends(RequirePermission(EQUIPMENT_READ)),
    db: Session = Depends(get_db),
) -> dict:
    q = db.query(Equipment).filter(Equipment.company_id == current_user.company_id)
    if owner_id:
        q = q.filter(Equipment.original_owner_id == owner_id)
    if category:
        q = q.filter(Equipment.category == category)
    if status_filter:
        q = q.filter(Equipment.status == status_filter)
    if barcode:
        q = q.filter(Equipment.barcode == barcode)
    if search:
        term = f"%{search.lower()}%"
        q = q.filter(
            or_(
                Equipment.serial_number.ilike(term),
                Equipment.model.ilike(term),
                Equipment.brand.ilike(term),
                Equipment.equipment_type.ilike(term),
                Equipment.manufacturer.ilike(term),
                Equipment.barcode.ilike(term),
            )
        )
    if brand:
        q = q.filter(Equipment.brand.ilike(f"%{brand}%"))
    total = q.count()
    items = (
        q.options(*_EQUIPMENT_LOAD_OPTS)
        .order_by(Equipment.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
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

    if payload.barcode:
        barcode_exists = (
            db.query(Equipment)
            .filter(
                Equipment.company_id == current_user.company_id,
                Equipment.barcode == payload.barcode,
            )
            .first()
        )
        if barcode_exists:
            raise HTTPException(status_code=400, detail="Código de barras duplicado en la empresa")

    if payload.original_owner_id:
        _validate_owner(db, current_user.company_id, payload.original_owner_id)

    data = payload.model_dump()
    eq = Equipment(company_id=current_user.company_id)
    apply_allowed_updates(eq, data, _EQUIPMENT_CREATE_ALLOWED)
    if eq.first_received_date is None:
        eq.first_received_date = date.today()
    db.add(eq)
    db.commit()
    db.refresh(eq)
    return _load_equipment(db, current_user.company_id, eq.id)


@router.get("/{equipment_id}", response_model=EquipmentResponse)
def get_equipment(
    equipment_id: UUID,
    current_user: User = Depends(RequirePermission(EQUIPMENT_READ)),
    db: Session = Depends(get_db),
) -> Equipment:
    eq = _load_equipment(db, current_user.company_id, equipment_id)
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

    eq = _load_equipment(db, current_user.company_id, equipment_id)
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

    new_barcode = data.get("barcode")
    if new_barcode and new_barcode != eq.barcode:
        exists = (
            db.query(Equipment)
            .filter(
                Equipment.company_id == current_user.company_id,
                Equipment.barcode == new_barcode,
                Equipment.id != equipment_id,
            )
            .first()
        )
        if exists:
            raise HTTPException(status_code=400, detail="Código de barras duplicado en la empresa")

    if data.get("original_owner_id"):
        _validate_owner(db, current_user.company_id, data["original_owner_id"])

    apply_allowed_updates(eq, data, _EQUIPMENT_UPDATE_ALLOWED)
    db.add(eq)
    db.commit()
    db.refresh(eq)
    return _load_equipment(db, current_user.company_id, equipment_id)


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


# ── Equipment Attributes (EAV) ──────────────────────────────────────────


@router.get("/{equipment_id}/attributes", response_model=list[EquipmentAttributeResponse])
def list_equipment_attributes(
    equipment_id: UUID,
    current_user: User = Depends(RequirePermission(EQUIPMENT_READ)),
    db: Session = Depends(get_db),
) -> list[EquipmentAttribute]:
    eq = _load_equipment(db, current_user.company_id, equipment_id)
    if not eq:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    return (
        db.query(EquipmentAttribute)
        .filter(EquipmentAttribute.equipment_id == equipment_id)
        .order_by(EquipmentAttribute.key)
        .all()
    )


@router.post("/{equipment_id}/attributes", response_model=EquipmentAttributeResponse, status_code=status.HTTP_201_CREATED)
def create_equipment_attribute(
    equipment_id: UUID,
    payload: EquipmentAttributeCreate,
    current_user: User = Depends(RequirePermission(EQUIPMENT_WRITE)),
    db: Session = Depends(get_db),
) -> EquipmentAttribute:
    ensure_not_viewer_for_mutation(current_user)
    eq = _load_equipment(db, current_user.company_id, equipment_id)
    if not eq:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")

    existing = (
        db.query(EquipmentAttribute)
        .filter(
            EquipmentAttribute.equipment_id == equipment_id,
            EquipmentAttribute.key == payload.key,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail=f"El atributo '{payload.key}' ya existe")

    attr = EquipmentAttribute(
        equipment_id=equipment_id,
        key=payload.key,
        value=payload.value,
        type=payload.type,
    )
    db.add(attr)
    db.commit()
    db.refresh(attr)
    return attr


@router.put("/{equipment_id}/attributes/{attr_id}", response_model=EquipmentAttributeResponse)
def update_equipment_attribute(
    equipment_id: UUID,
    attr_id: UUID,
    payload: EquipmentAttributeUpdate,
    current_user: User = Depends(RequirePermission(EQUIPMENT_WRITE)),
    db: Session = Depends(get_db),
) -> EquipmentAttribute:
    ensure_not_viewer_for_mutation(current_user)
    eq = _load_equipment(db, current_user.company_id, equipment_id)
    if not eq:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")

    attr = (
        db.query(EquipmentAttribute)
        .filter(EquipmentAttribute.id == attr_id, EquipmentAttribute.equipment_id == equipment_id)
        .first()
    )
    if not attr:
        raise HTTPException(status_code=404, detail="Atributo no encontrado")

    data = payload.model_dump(exclude_unset=True)
    if "value" in data:
        attr.value = data["value"]
    if "type" in data:
        attr.type = data["type"]
    db.add(attr)
    db.commit()
    db.refresh(attr)
    return attr


@router.delete("/{equipment_id}/attributes/{attr_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_equipment_attribute(
    equipment_id: UUID,
    attr_id: UUID,
    current_user: User = Depends(RequirePermission(EQUIPMENT_WRITE)),
    db: Session = Depends(get_db),
) -> None:
    ensure_not_viewer_for_mutation(current_user)
    eq = _load_equipment(db, current_user.company_id, equipment_id)
    if not eq:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")

    attr = (
        db.query(EquipmentAttribute)
        .filter(EquipmentAttribute.id == attr_id, EquipmentAttribute.equipment_id == equipment_id)
        .first()
    )
    if not attr:
        raise HTTPException(status_code=404, detail="Atributo no encontrado")
    db.delete(attr)
    db.commit()


# ── Helpers ──────────────────────────────────────────────────────────────


def _validate_owner(db: Session, company_id: UUID, owner_id: UUID) -> None:
    owner = (
        db.query(Customer)
        .filter(Customer.id == owner_id, Customer.company_id == company_id)
        .first()
    )
    if not owner:
        raise HTTPException(status_code=400, detail="Propietario original no válido")


_EQUIPMENT_CREATE_ALLOWED = (
    "serial_number", "equipment_type", "category", "subcategory",
    "brand", "model", "manufacturer", "manufacturer_part_number",
    "imei", "color", "barcode", "original_owner_id", "status",
    "location", "parent_equipment_id", "supplier_id",
    "purchase_date", "purchase_price", "warranty_start",
    "warranty_end", "warranty_provider",
    "photos_urls", "image_urls", "tags", "custom_fields",
    "additional_notes", "first_received_date",
)

_EQUIPMENT_UPDATE_ALLOWED = _EQUIPMENT_CREATE_ALLOWED
