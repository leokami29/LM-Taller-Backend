from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.enums import UserRole
from app.schemas.rbac import UserSiteRoleInput


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str = Field(..., min_length=8)
    role: UserRole = UserRole.RECEPTION
    phone: Optional[str] = None


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    phone: Optional[str]
    avatar_url: Optional[str]
    last_login: Optional[datetime]
    created_at: datetime


class UserAdminCreate(UserCreate):
    """Creación de usuario por admin (misma forma que UserCreate)."""

    site_roles: list[UserSiteRoleInput] = Field(default_factory=list)


class UserPasswordUpdate(BaseModel):
    password: str = Field(..., min_length=8)
