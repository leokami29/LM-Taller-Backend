from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.platform_user import PlatformUser
from app.db.session import get_db
from app.schemas.platform import PlatformLoginRequest, PlatformUserResponse
from app.schemas.tokens import PlatformTokenPairResponse, RefreshTokenRequest
from app.services.audit_service import write_audit
from app.services.catalog_audit_service import write_catalog_audit
from app.services.platform_auth_service import (
    authenticate_platform_user,
    create_platform_token_pair,
    refresh_platform_tokens,
)

router = APIRouter(prefix="/auth", tags=["platform-auth"])


def _pair_response(user: PlatformUser, access: str, refresh: str) -> PlatformTokenPairResponse:
    return PlatformTokenPairResponse(
        access_token=access,
        refresh_token=refresh,
        user=PlatformUserResponse.model_validate(user),
    )


def _write_platform_login_audit(db: Session, request: Request, user_id: str) -> None:
    ip = request.client.host if request.client else None
    if settings.USE_TENANT_DATABASE_ROUTING:
        write_catalog_audit(
            db,
            actor_type="platform",
            actor_id=user_id,
            action="platform.login",
            ip_address=ip,
        )
    else:
        write_audit(
            db,
            actor_type="platform",
            actor_id=user_id,
            action="platform.login",
            ip_address=ip,
        )


@router.post("/login", response_model=PlatformTokenPairResponse)
def platform_login_json(
    payload: PlatformLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> PlatformTokenPairResponse:
    user = authenticate_platform_user(db, str(payload.email), payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario desactivado")
    access, refresh = create_platform_token_pair(user)
    _write_platform_login_audit(db, request, str(user.id))
    db.commit()
    return _pair_response(user, access, refresh)


@router.post("/token", response_model=PlatformTokenPairResponse)
def platform_login_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> PlatformTokenPairResponse:
    user = authenticate_platform_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario desactivado")
    access, refresh = create_platform_token_pair(user)
    _write_platform_login_audit(db, request, str(user.id))
    db.commit()
    return _pair_response(user, access, refresh)


@router.post("/refresh", response_model=PlatformTokenPairResponse)
def platform_refresh(
    payload: RefreshTokenRequest,
    db: Session = Depends(get_db),
) -> PlatformTokenPairResponse:
    out = refresh_platform_tokens(db, payload.refresh_token)
    if not out:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh inválido")
    access, refresh, user = out
    return _pair_response(user, access, refresh)
