from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import SecurityUtils
from app.dependencies import get_current_admin
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.user import UserAdminCreate, UserPasswordUpdate, UserResponse, UserUpdate

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=List[UserResponse])
def list_company_users(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> List[User]:
    return db.query(User).filter(User.company_id == admin.company_id).order_by(User.created_at.desc()).all()


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_company_user(
    payload: UserAdminCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> User:
    exists = (
        db.query(User)
        .filter(User.company_id == admin.company_id, User.email == str(payload.email))
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="El email ya está registrado en la empresa")

    user = User(
        company_id=admin.company_id,
        email=str(payload.email),
        full_name=payload.full_name,
        hashed_password=SecurityUtils.hash_password(payload.password),
        role=payload.role,
        phone=payload.phone,
        created_by_id=admin.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}", response_model=UserResponse)
def update_company_user(
    user_id: UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> User:
    user = (
        db.query(User)
        .filter(User.id == user_id, User.company_id == admin.company_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(user, k, v)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}/password", response_model=UserResponse)
def reset_user_password(
    user_id: UUID,
    payload: UserPasswordUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> User:
    user = (
        db.query(User)
        .filter(User.id == user_id, User.company_id == admin.company_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    user.hashed_password = SecurityUtils.hash_password(payload.password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
