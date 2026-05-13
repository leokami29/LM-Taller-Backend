from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import UUID

import bcrypt
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from app.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")
platform_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/platform/v1/auth/token")

TOKEN_USE_ACCESS = "access"
TOKEN_USE_REFRESH = "refresh"
TYP_TENANT = "tenant"
TYP_PLATFORM = "platform"


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
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.setdefault("token_use", TOKEN_USE_ACCESS)
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    @staticmethod
    def create_refresh_token(data: dict[str, Any]) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire, "token_use": TOKEN_USE_REFRESH})
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    @staticmethod
    def decode_token(token: str) -> Optional[dict[str, Any]]:
        try:
            return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        except JWTError:
            return None

    @staticmethod
    def create_tenant_access_token(user_id: UUID, company_id: UUID) -> str:
        return SecurityUtils.create_access_token(
            {
                "sub": str(user_id),
                "typ": TYP_TENANT,
                "company_id": str(company_id),
                "token_use": TOKEN_USE_ACCESS,
            }
        )

    @staticmethod
    def create_tenant_refresh_token(user_id: UUID, company_id: UUID) -> str:
        return SecurityUtils.create_refresh_token(
            {
                "sub": str(user_id),
                "typ": TYP_TENANT,
                "rtyp": TYP_TENANT,
                "company_id": str(company_id),
            }
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
        return SecurityUtils.create_access_token(data)

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
        return SecurityUtils.create_refresh_token(data)
