from collections.abc import Generator

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db.rls import apply_rls_session_context

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=Session)


def get_db(request: Request) -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        apply_rls_session_context(db, request.headers.get("Authorization"))
        yield db
    finally:
        db.close()
