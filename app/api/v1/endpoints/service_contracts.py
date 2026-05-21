from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.permissions import CONTRACTS_READ, CONTRACTS_WRITE
from app.dependencies import RequirePermission, get_permission_context, PermissionContext
from app.db.models.service_contract import ServiceContract
from app.db.session import get_db
from app.schemas.common import PaginatedResponse
from app.schemas.service_contract import (
    ServiceContractCreate,
    ServiceContractResponse,
    ServiceContractUpdate,
)
from app.services.contract_service import create_contract, get_contract_for_company, update_contract

router = APIRouter(prefix="/service-contracts", tags=["service-contracts"])


@router.get("/", response_model=PaginatedResponse[ServiceContractResponse])
def list_service_contracts(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    customer_id: Optional[UUID] = Query(None),
    active_only: bool = Query(False),
    ctx: PermissionContext = Depends(RequirePermission(CONTRACTS_READ)),
    db: Session = Depends(get_db),
) -> dict:
    q = db.query(ServiceContract).filter(ServiceContract.company_id == ctx.company_id)
    if customer_id:
        q = q.filter(ServiceContract.customer_id == customer_id)
    if active_only:
        q = q.filter(ServiceContract.is_active.is_(True))
    total = q.count()
    items = q.order_by(ServiceContract.contract_number).offset(skip).limit(limit).all()
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.post("/", response_model=ServiceContractResponse, status_code=status.HTTP_201_CREATED)
def create_service_contract(
    payload: ServiceContractCreate,
    ctx: PermissionContext = Depends(RequirePermission(CONTRACTS_WRITE)),
    db: Session = Depends(get_db),
) -> ServiceContract:
    try:
        row = create_contract(
            db,
            company_id=ctx.company_id,
            customer_id=payload.customer_id,
            contract_number=payload.contract_number,
            name=payload.name,
            contract_kind=payload.contract_kind,
            default_site_id=payload.default_site_id,
            allowed_order_kinds=payload.allowed_order_kinds,
            template_json=payload.template_json,
            max_orders_per_month=payload.max_orders_per_month,
            valid_from=payload.valid_from,
            valid_to=payload.valid_to,
            is_active=payload.is_active,
        )
        db.commit()
        db.refresh(row)
        return row
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{contract_id}", response_model=ServiceContractResponse)
def get_service_contract(
    contract_id: UUID,
    ctx: PermissionContext = Depends(RequirePermission(CONTRACTS_READ)),
    db: Session = Depends(get_db),
) -> ServiceContract:
    row = get_contract_for_company(db, company_id=ctx.company_id, contract_id=contract_id)
    if not row:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    return row


@router.put("/{contract_id}", response_model=ServiceContractResponse)
def update_service_contract(
    contract_id: UUID,
    payload: ServiceContractUpdate,
    ctx: PermissionContext = Depends(RequirePermission(CONTRACTS_WRITE)),
    db: Session = Depends(get_db),
) -> ServiceContract:
    row = get_contract_for_company(db, company_id=ctx.company_id, contract_id=contract_id)
    if not row:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    try:
        update_contract(db, contract=row, data=payload.model_dump(exclude_unset=True))
        db.commit()
        db.refresh(row)
        return row
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
