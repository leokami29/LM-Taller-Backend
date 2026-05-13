from fastapi import APIRouter

from app.api.platform.v1.endpoints import auth as platform_auth
from app.api.platform.v1.endpoints import companies as platform_companies
from app.api.platform.v1.endpoints import impersonate as platform_impersonate

router = APIRouter(prefix="/api/platform/v1")

router.include_router(platform_auth.router)
router.include_router(platform_companies.router)
router.include_router(platform_impersonate.router)
