from fastapi import APIRouter, HTTPException, Request, status

from app.schemas.public_tracking import PublicOrderTrackingResponse
from app.services.public_tracking_service import get_public_order_tracking
from app.services.rate_limit_service import public_tracking_rate_limiter

router = APIRouter(prefix="/public", tags=["public-tracking"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


@router.get(
    "/seguimiento/{tenant_slug}/{tracking_code}",
    response_model=PublicOrderTrackingResponse,
)
def public_order_tracking(
    tenant_slug: str,
    tracking_code: str,
    request: Request,
) -> PublicOrderTrackingResponse:
    limiter = public_tracking_rate_limiter()
    ip = _client_ip(request)
    if not limiter.is_allowed(f"public-tracking:{ip}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiadas solicitudes. Intente más tarde.",
        )

    try:
        return get_public_order_tracking(tenant_slug=tenant_slug, tracking_code=tracking_code)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
