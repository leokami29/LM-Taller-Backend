from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import TYP_PORTAL, SecurityUtils
from app.db.session import SessionLocal, tenant_session_for_company, tenant_session_for_slug
from app.schemas.portal import PortalLoginRequest, PortalTokenPairResponse, PortalUserResponse
from app.schemas.tokens import RefreshTokenRequest
from app.services.portal_auth_service import (
    authenticate_portal_user,
    create_portal_token_pair,
    refresh_portal_tokens,
)
from app.tenancy import TenantResolveError

router = APIRouter(prefix="/auth", tags=["portal-auth"])


def _login_in_db(db: Session, email: str, password: str) -> PortalTokenPairResponse:
    user = authenticate_portal_user(db, email, password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
    try:
        access, refresh = create_portal_token_pair(user, db)
        db.commit()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    return PortalTokenPairResponse(
        access_token=access,
        refresh_token=refresh,
        user=PortalUserResponse.model_validate(user),
        customer_id=user.customer_id,
    )


def _company_id_from_portal_refresh(refresh_token: str):
    payload = SecurityUtils.decode_token(refresh_token)
    if not payload or payload.get("token_use") != "refresh":
        return None
    if payload.get("rtyp") != TYP_PORTAL and payload.get("typ") != TYP_PORTAL:
        return None
    raw = payload.get("company_id")
    if not raw:
        return None
    from uuid import UUID

    try:
        return UUID(str(raw))
    except ValueError:
        return None


@router.post("/login", response_model=PortalTokenPairResponse)
def portal_login(payload: PortalLoginRequest) -> PortalTokenPairResponse:
    if settings.USE_TENANT_DATABASE_ROUTING:
        if not payload.tenant_slug or not payload.tenant_slug.strip():
            raise HTTPException(status_code=400, detail="tenant_slug es obligatorio")
        try:
            with tenant_session_for_slug(payload.tenant_slug.strip()) as tdb:
                return _login_in_db(tdb, payload.email, payload.password)
        except TenantResolveError as exc:
            raise HTTPException(status_code=400, detail="Taller no encontrado") from exc
    db = SessionLocal()
    try:
        return _login_in_db(db, payload.email, payload.password)
    finally:
        db.close()


@router.post("/token", response_model=PortalTokenPairResponse)
def portal_token(
    form: OAuth2PasswordRequestForm = Depends(),
    tenant_slug: str | None = None,
) -> PortalTokenPairResponse:
    payload = PortalLoginRequest(email=form.username, password=form.password, tenant_slug=tenant_slug)
    if settings.USE_TENANT_DATABASE_ROUTING:
        if not payload.tenant_slug:
            raise HTTPException(status_code=400, detail="tenant_slug es obligatorio")
        with tenant_session_for_slug(payload.tenant_slug.strip()) as tdb:
            return _login_in_db(tdb, payload.email, payload.password)
    db = SessionLocal()
    try:
        return _login_in_db(db, payload.email, payload.password)
    finally:
        db.close()


@router.post("/refresh", response_model=PortalTokenPairResponse)
def portal_refresh(body: RefreshTokenRequest) -> PortalTokenPairResponse:
    company_id = _company_id_from_portal_refresh(body.refresh_token)
    if company_id is None:
        raise HTTPException(status_code=401, detail="Refresh token inválido")
    with tenant_session_for_company(company_id) as db:
        result = refresh_portal_tokens(db, body.refresh_token)
        if not result:
            raise HTTPException(status_code=401, detail="Refresh token inválido")
        access, refresh, user = result
        db.commit()
        return PortalTokenPairResponse(
            access_token=access,
            refresh_token=refresh,
            user=PortalUserResponse.model_validate(user),
            customer_id=user.customer_id,
        )
