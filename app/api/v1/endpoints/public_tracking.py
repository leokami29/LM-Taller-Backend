from fastapi import APIRouter, HTTPException, Request, status

from app.schemas.public_tracking import PublicOrderTrackingResponse
from app.services.public_tracking_service import get_public_order_tracking
from app.services.rate_limit_service import public_tracking_rate_limiter

router = APIRouter(prefix="/public", tags=["public-tracking"])


def _client_ip(request: Request) -> str:
    """IP del cliente. Solo usa X-Forwarded-For si hay proxy confiable (header X-Trusted-Proxy)."""
    # Si el despliegue está detrás de un reverse proxy que elimina XFF del cliente,
    # puede inyectar X-Real-IP. No confiamos en XFF arbitrario del atacante.
    real_ip = request.headers.get("X-Real-IP")
    if real_ip and real_ip.strip():
        return real_ip.strip()
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
    slug_key = (tenant_slug or "").strip().lower()[:64]
    if not limiter.is_allowed(f"public-tracking:{ip}:{slug_key}"):
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
