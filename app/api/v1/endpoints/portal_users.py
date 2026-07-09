from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.permissions import PORTAL_USERS_READ, PORTAL_USERS_WRITE
from app.core.security import SecurityUtils
from app.db.models.customer_portal_user import CustomerPortalUser
from app.db.session import get_db
from app.dependencies import PermissionContext, RequirePermission
from app.schemas.portal import PortalUserCreate, PortalUserCreateResponse, PortalUserPatch, PortalUserResponse
from app.services.portal_auth_service import create_portal_user

router = APIRouter(prefix="/admin/portal-users", tags=["portal-users"])


@router.get("/", response_model=List[PortalUserResponse])
def list_portal_users(
    customer_id: Optional[UUID] = Query(None),
    ctx: PermissionContext = Depends(RequirePermission(PORTAL_USERS_READ)),
    db: Session = Depends(get_db),
) -> List[CustomerPortalUser]:
    q = db.query(CustomerPortalUser).filter(CustomerPortalUser.company_id == ctx.company_id)
    if customer_id:
        q = q.filter(CustomerPortalUser.customer_id == customer_id)
    return q.order_by(CustomerPortalUser.email).all()


@router.post("/", response_model=PortalUserCreateResponse, status_code=status.HTTP_201_CREATED)
def invite_portal_user(
    payload: PortalUserCreate,
    ctx: PermissionContext = Depends(RequirePermission(PORTAL_USERS_WRITE)),
    db: Session = Depends(get_db),
) -> dict:
    try:
        row = create_portal_user(
            db,
            company_id=ctx.company_id,
            customer_id=payload.customer_id,
            email=payload.email,
            full_name=payload.full_name,
            password=payload.password,
            invited_by_id=ctx.user_id,
        )
        db.commit()
        db.refresh(row)
        return {"user": row, "temporary_password": payload.password}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.patch("/{portal_user_id}", response_model=PortalUserResponse)
def patch_portal_user(
    portal_user_id: UUID,
    payload: PortalUserPatch,
    ctx: PermissionContext = Depends(RequirePermission(PORTAL_USERS_WRITE)),
    db: Session = Depends(get_db),
) -> CustomerPortalUser:
    row = (
        db.query(CustomerPortalUser)
        .filter(
            CustomerPortalUser.id == portal_user_id,
            CustomerPortalUser.company_id == ctx.company_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Usuario portal no encontrado")
    data = payload.model_dump(exclude_unset=True)
    if "password" in data and data["password"]:
        row.hashed_password = SecurityUtils.hash_password(data.pop("password"))
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row
