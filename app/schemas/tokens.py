from pydantic import BaseModel

from app.schemas.platform import PlatformUserResponse
from app.schemas.user import UserResponse


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TenantTokenPairResponse(TokenPairResponse):
    user: UserResponse


class PlatformTokenPairResponse(TokenPairResponse):
    user: PlatformUserResponse
