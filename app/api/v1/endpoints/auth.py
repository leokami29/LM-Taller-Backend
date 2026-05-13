from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models.user import User
from app.dependencies import get_current_user
from app.schemas.tokens import RefreshTokenRequest, TenantTokenPairResponse
from app.schemas.user import UserResponse
from app.services.auth_service import (
    authenticate_user,
    create_tenant_token_pair,
    refresh_tenant_tokens,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def _token_pair(user: User) -> TenantTokenPairResponse:
    access, refresh = create_tenant_token_pair(user)
    return TenantTokenPairResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=TenantTokenPairResponse)
def login_json(payload: LoginRequest, db: Session = Depends(get_db)) -> TenantTokenPairResponse:
    user = authenticate_user(db, str(payload.email), payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email o contraseña incorrectos")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario desactivado")
    return _token_pair(user)


@router.post("/token", response_model=TenantTokenPairResponse)
def login_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TenantTokenPairResponse:
    """Compatibilidad OAuth2 (Swagger): username = email."""
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email o contraseña incorrectos")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario desactivado")
    return _token_pair(user)


@router.post("/refresh", response_model=TenantTokenPairResponse)
def refresh_access_token(
    payload: RefreshTokenRequest,
    db: Session = Depends(get_db),
) -> TenantTokenPairResponse:
    out = refresh_tenant_tokens(db, payload.refresh_token)
    if not out:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido o expirado")
    access, refresh, user = out
    return TenantTokenPairResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def read_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
