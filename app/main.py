import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.platform.v1.router import router as platform_v1_router
from app.api.v1.router import router as api_v1_router
from app.config import settings
from app.infrastructure.redis_client import connect_redis, disconnect_redis_async
from app.middleware.error_handler import register_exception_handlers
from app.middleware.logging import RequestLoggingMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    connect_redis()
    try:
        yield
    finally:
        await disconnect_redis_async()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

register_exception_handlers(app)

app.add_middleware(RequestLoggingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router)
app.include_router(platform_v1_router)


@app.get("/health")
def health_check() -> dict:
    from app.infrastructure.redis_client import get_sync_redis

    payload: dict = {"status": "ok", "version": settings.APP_VERSION}
    payload["redis"] = "ok" if get_sync_redis() is not None else "degraded"
    if settings.USE_TENANT_DATABASE_ROUTING:
        from app.tenancy.metrics import snapshot as tenant_resolution_metrics

        payload["tenant_resolution_metrics"] = tenant_resolution_metrics()
    return payload


@app.get("/")
def root() -> dict:
    return {
        "message": "SGtaller Web API",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "redoc": "/redoc",
    }
