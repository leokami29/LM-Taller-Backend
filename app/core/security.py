from datetime import timedelta
from typing import Any, Optional
from uuid import UUID

import bcrypt
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from app.config import settings
from app.core.dt import utc_now
from app.services.platform_config_service import get_session_settings
from app.services.session_policy_service import ResolvedSession

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")
platform_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/platform/v1/auth/token")

TOKEN_USE_ACCESS = "access"
TOKEN_USE_REFRESH = "refresh"
TYP_TENANT = "tenant"
TYP_PLATFORM = "platform"
TYP_PORTAL = "portal"

portal_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/portal/auth/token")


class SecurityUtils:
    @staticmethod
    def hash_password(password: str) -> str:
        pw = password.encode("utf-8")
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(pw, salt).decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        if not hashed_password:
            return False
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"),
                hashed_password.encode("utf-8"),
            )
        except ValueError:
            return False

    @staticmethod
    def create_access_token(
        data: dict[str, Any],
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        to_encode = data.copy()
        if expires_delta:
            expire = utc_now() + expires_delta
        else:
            expire = utc_now() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.setdefault("token_use", TOKEN_USE_ACCESS)
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    @staticmethod
    def create_refresh_token(
        data: dict[str, Any],
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        to_encode = data.copy()
        if expires_delta:
            expire = utc_now() + expires_delta
        else:
            expire = utc_now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire, "token_use": TOKEN_USE_REFRESH})
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    @staticmethod
    def decode_token(token: str) -> Optional[dict[str, Any]]:
        try:
            return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        except JWTError:
            return None

    @staticmethod
    def create_tenant_access_token(
        user_id: UUID,
        company_id: UUID,
        *,
        resolved: ResolvedSession | None = None,
    ) -> str:
        if resolved is None:
            session = get_session_settings()
            minutes = session.tenant_access_token_minutes
        else:
            minutes = resolved.access_token_minutes
        return SecurityUtils.create_access_token(
            {
                "sub": str(user_id),
                "typ": TYP_TENANT,
                "company_id": str(company_id),
                "token_use": TOKEN_USE_ACCESS,
            },
            expires_delta=timedelta(minutes=minutes),
        )

    @staticmethod
    def create_tenant_refresh_token(
        user_id: UUID,
        company_id: UUID,
        *,
        resolved: ResolvedSession | None = None,
    ) -> str:
        if resolved is None:
            session = get_session_settings()
            days = session.tenant_refresh_token_days
        else:
            days = resolved.refresh_token_days
        return SecurityUtils.create_refresh_token(
            {
                "sub": str(user_id),
                "typ": TYP_TENANT,
                "rtyp": TYP_TENANT,
                "company_id": str(company_id),
            },
            expires_delta=timedelta(days=days),
        )

    @staticmethod
    def create_platform_access_token(
        user_id: UUID,
        role: str,
        act_as_company_id: Optional[UUID] = None,
    ) -> str:
        data: dict[str, Any] = {
            "sub": str(user_id),
            "typ": TYP_PLATFORM,
            "role": role,
            "token_use": TOKEN_USE_ACCESS,
        }
        if act_as_company_id:
            data["act_as_company_id"] = str(act_as_company_id)
        session = get_session_settings()
        return SecurityUtils.create_access_token(
            data,
            expires_delta=timedelta(minutes=session.platform_access_token_minutes),
        )

    @staticmethod
    def create_platform_refresh_token(
        user_id: UUID,
        role: str,
        act_as_company_id: Optional[UUID] = None,
    ) -> str:
        data: dict[str, Any] = {
            "sub": str(user_id),
            "typ": TYP_PLATFORM,
            "rtyp": TYP_PLATFORM,
            "role": role,
        }
        if act_as_company_id:
            data["act_as_company_id"] = str(act_as_company_id)
        session = get_session_settings()
        return SecurityUtils.create_refresh_token(
            data,
            expires_delta=timedelta(days=session.platform_refresh_token_days),
        )

    @staticmethod
    def create_portal_access_token(
        portal_user_id: UUID,
        company_id: UUID,
        customer_id: UUID,
    ) -> str:
        session = get_session_settings()
        return SecurityUtils.create_access_token(
            {
                "sub": str(portal_user_id),
                "typ": TYP_PORTAL,
                "company_id": str(company_id),
                "customer_id": str(customer_id),
                "token_use": TOKEN_USE_ACCESS,
            },
            expires_delta=timedelta(minutes=session.tenant_access_token_minutes),
        )

    @staticmethod
    def create_portal_refresh_token(
        portal_user_id: UUID,
        company_id: UUID,
        customer_id: UUID,
    ) -> str:
        session = get_session_settings()
        return SecurityUtils.create_refresh_token(
            {
                "sub": str(portal_user_id),
                "typ": TYP_PORTAL,
                "rtyp": TYP_PORTAL,
                "company_id": str(company_id),
                "customer_id": str(customer_id),
            },
            expires_delta=timedelta(days=session.tenant_refresh_token_days),
        )
