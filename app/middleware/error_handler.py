import logging

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import DomainError

logger = logging.getLogger(__name__)


def _integrity_error_payload(exc: IntegrityError) -> tuple[int, str, str]:
    """Traduce códigos PostgreSQL comunes a respuesta API legible."""
    orig = getattr(exc, "orig", None)
    pgcode = getattr(orig, "pgcode", None)
    if pgcode == "23514":
        return (
            status.HTTP_400_BAD_REQUEST,
            "Los datos no son coherentes entre la empresa del taller y los recursos enlazados "
            "(por ejemplo orden, cliente, inventario o usuario). Revisa que todo pertenezca al mismo taller.",
            "tenant_integrity_violation",
        )
    if pgcode == "23503":
        return (
            status.HTTP_400_BAD_REQUEST,
            "No se puede guardar: falta un registro relacionado o fue eliminado.",
            "foreign_key_violation",
        )
    if pgcode == "23505":
        return (
            status.HTTP_409_CONFLICT,
            "Ya existe un registro con ese identificador único en el taller.",
            "unique_violation",
        )
    logger.warning("IntegrityError sin mapeo específico: %s", exc)
    return (
        status.HTTP_400_BAD_REQUEST,
        "No se pudo guardar por una restricción de base de datos.",
        "integrity_error",
    )


def register_exception_handlers(app) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": exc.message, "code": exc.code},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors(), "message": "Error de validación"},
        )

    @app.exception_handler(IntegrityError)
    async def sqlalchemy_integrity_handler(_: Request, exc: IntegrityError) -> JSONResponse:
        code, detail, err_code = _integrity_error_payload(exc)
        return JSONResponse(status_code=code, content={"detail": detail, "code": err_code})
