from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.user import User
from app.db.session import (
    SessionLocal,
    decode_refresh_company_id,
    get_db,
    tenant_session_for_company,
    tenant_session_for_slug,
)
from app.dependencies import get_current_user
from app.schemas.tokens import RefreshTokenRequest, TenantTokenPairResponse
from app.schemas.user import UserResponse
from app.schemas.session_policy import SessionEffectiveSchema
from app.services.auth_service import (
    authenticate_user,
    create_tenant_token_pair,
    refresh_tenant_tokens,
)
from app.services.session_policy_service import ResolvedSession
from app.tenancy import TenantResolveError

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    tenant_slug: Optional[str] = Field(
        default=None,
        description="Obligatorio si USE_TENANT_DATABASE_ROUTING=true (slug del taller en catálogo).",
    )


def _resolved_to_schema(resolved: ResolvedSession) -> SessionEffectiveSchema:
    return SessionEffectiveSchema(
        access_token_minutes=resolved.access_token_minutes,
        refresh_token_days=resolved.refresh_token_days,
        source=resolved.source,
    )


def _token_pair(user: User, *, site_id=None) -> TenantTokenPairResponse:
    if settings.USE_TENANT_DATABASE_ROUTING:
        with tenant_session_for_company(user.company_id) as db:
            access, refresh, resolved = create_tenant_token_pair(user, db, site_id=site_id)
    else:
        db = SessionLocal()
        try:
            access, refresh, resolved = create_tenant_token_pair(user, db, site_id=site_id)
        finally:
            db.close()
    return TenantTokenPairResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserResponse.model_validate(user),
        session_effective=_resolved_to_schema(resolved),
    )


def _authenticate_tenant_user(email: str, password: str, tenant_slug: Optional[str]) -> User:
    if settings.USE_TENANT_DATABASE_ROUTING:
        if not tenant_slug or not tenant_slug.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="tenant_slug es obligatorio cuando el routing por base de datos por tenant está activo",
            )
        try:
            with tenant_session_for_slug(tenant_slug.strip()) as db:
                user = authenticate_user(db, email, password)
        except TenantResolveError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Taller no encontrado o inactivo",
            ) from exc
    else:
        db = SessionLocal()
        try:
            user = authenticate_user(db, email, password)
        finally:
            db.close()
    return user


@router.post("/login", response_model=TenantTokenPairResponse)
def login_json(payload: LoginRequest) -> TenantTokenPairResponse:
    user = _authenticate_tenant_user(str(payload.email), payload.password, payload.tenant_slug)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email o contraseña incorrectos")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario desactivado")
    return _token_pair(user)


@router.post("/token", response_model=TenantTokenPairResponse)
def login_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    tenant_slug: Annotated[Optional[str], Query(description="Obligatorio con routing por tenant")] = None,
) -> TenantTokenPairResponse:
    """Compatibilidad OAuth2 (Swagger): username = email. Con routing por tenant, añadir query tenant_slug."""
    user = _authenticate_tenant_user(form_data.username, form_data.password, tenant_slug)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email o contraseña incorrectos")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario desactivado")
    return _token_pair(user)


@router.post("/refresh", response_model=TenantTokenPairResponse)
def refresh_access_token(payload: RefreshTokenRequest) -> TenantTokenPairResponse:
    company_id = decode_refresh_company_id(payload.refresh_token)
    if company_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido o expirado",
        )
    with tenant_session_for_company(company_id) as db:
        out = refresh_tenant_tokens(db, payload.refresh_token, site_id=payload.site_id)
    if not out:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido o expirado")
    access, refresh, user, resolved = out
    return TenantTokenPairResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserResponse.model_validate(user),
        session_effective=_resolved_to_schema(resolved),
    )


@router.get("/me", response_model=UserResponse)
def read_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
