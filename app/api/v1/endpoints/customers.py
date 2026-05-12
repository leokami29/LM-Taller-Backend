from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.enums import UserRole
from app.dependencies import ensure_not_viewer_for_mutation, get_current_admin, get_current_user
from app.db.models.customer import Customer
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.common import PaginatedResponse
from app.schemas.customer import CustomerCreate, CustomerResponse, CustomerUpdate

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("/", response_model=PaginatedResponse[CustomerResponse])
def list_customers(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(None, description="Busca en nombre, apellido o email"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    q = db.query(Customer).filter(Customer.company_id == current_user.company_id)
    if search:
        term = f"%{search.lower()}%"
        q = q.filter(
            or_(
                Customer.email.ilike(term),
                Customer.first_name.ilike(term),
                Customer.last_name.ilike(term),
            )
        )
    total = q.count()
    items = q.order_by(Customer.created_at.desc()).offset(skip).limit(limit).all()
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.post("/", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: CustomerCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Customer:
    ensure_not_viewer_for_mutation(current_user)
    if current_user.role == UserRole.TECHNICIAN:
        raise HTTPException(status_code=403, detail="Los técnicos no pueden crear clientes")

    if payload.email:
        existing = (
            db.query(Customer)
            .filter(
                Customer.company_id == current_user.company_id,
                Customer.email == str(payload.email),
            )
            .first()
        )
        if existing:
            raise HTTPException(status_code=400, detail="Email ya existe para esta empresa")

    customer = Customer(
        company_id=current_user.company_id,
        **payload.model_dump(),
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer(
    customer_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Customer:
    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.company_id == current_user.company_id)
        .first()
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return customer


@router.put("/{customer_id}", response_model=CustomerResponse)
def update_customer(
    customer_id: UUID,
    payload: CustomerUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Customer:
    ensure_not_viewer_for_mutation(current_user)
    if current_user.role == UserRole.TECHNICIAN:
        raise HTTPException(status_code=403, detail="Los técnicos no pueden editar clientes")

    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.company_id == current_user.company_id)
        .first()
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    data = payload.model_dump(exclude_unset=True)
    new_email = data.get("email")
    if new_email:
        existing = (
            db.query(Customer)
            .filter(
                Customer.company_id == current_user.company_id,
                Customer.email == str(new_email),
                Customer.id != customer_id,
            )
            .first()
        )
        if existing:
            raise HTTPException(status_code=400, detail="Email ya existe para esta empresa")

    for k, v in data.items():
        setattr(customer, k, v)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@router.delete("/{customer_id}", status_code=status.HTTP_200_OK)
def delete_customer(
    customer_id: UUID,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.company_id == admin.company_id)
        .first()
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    db.delete(customer)
    db.commit()
    return {"message": "Cliente eliminado exitosamente", "status": "success"}
