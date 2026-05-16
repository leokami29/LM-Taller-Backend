from fastapi import APIRouter

from app.api.platform.v1.endpoints import auth as platform_auth
from app.api.platform.v1.endpoints import companies as platform_companies
from app.api.platform.v1.endpoints import impersonate as platform_impersonate
from app.api.platform.v1.endpoints import stripe_webhook
from app.api.platform.v1.endpoints import subscriptions as platform_subscriptions
from app.api.platform.v1.endpoints import analytics as platform_analytics
from app.api.platform.v1.endpoints import config as platform_config

router = APIRouter(prefix="/api/platform/v1")

router.include_router(platform_auth.router)
router.include_router(platform_companies.router)
router.include_router(platform_subscriptions.router)
router.include_router(platform_impersonate.router)
router.include_router(stripe_webhook.router)
router.include_router(platform_analytics.router)
router.include_router(platform_config.router)
