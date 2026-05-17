from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.schemas.platform import PlatformUserResponse
from app.schemas.session_policy import SessionEffectiveSchema
from app.schemas.user import UserResponse


class RefreshTokenRequest(BaseModel):
    refresh_token: str
    site_id: Optional[UUID] = None


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TenantTokenPairResponse(TokenPairResponse):
    user: UserResponse
    session_effective: SessionEffectiveSchema


class PlatformTokenPairResponse(TokenPairResponse):
    user: PlatformUserResponse
