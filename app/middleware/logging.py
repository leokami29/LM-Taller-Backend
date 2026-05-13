import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("sgtaller.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request_id=%s method=%s path=%s", request_id, request.method, request.url.path)
            raise
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        tenant = getattr(request.state, "tenant_company_id", None)
        tenant_part = f" tenant_company_id={tenant}" if tenant else ""
        logger.info(
            "request_id=%s method=%s path=%s status=%s elapsed_ms=%.2f%s",
            request_id,
            request.method,
            request.url.path,
            getattr(response, "status_code", "?"),
            elapsed_ms,
            tenant_part,
        )
        return response
