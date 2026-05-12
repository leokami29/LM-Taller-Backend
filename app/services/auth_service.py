from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import SecurityUtils
from app.db.models.user import User


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None
    if not SecurityUtils.verify_password(password, user.hashed_password):
        return None
    return user


def create_access_token_for_user(user: User) -> str:
    expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return SecurityUtils.create_access_token({"sub": str(user.id)}, expires_delta=expires)
