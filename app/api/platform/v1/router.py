from fastapi import APIRouter

from app.api.platform.v1.endpoints import auth as platform_auth
from app.api.platform.v1.endpoints import companies as platform_companies
from app.api.platform.v1.endpoints import impersonate as platform_impersonate
from app.api.platform.v1.endpoints import stripe_webhook
from app.api.platform.v1.endpoints import subscriptions as platform_subscriptions
from app.api.platform.v1.endpoints import analytics as platform_analytics
from app.api.platform.v1.endpoints import config as platform_config
from app.api.platform.v1.endpoints import installations as platform_installations
from app.api.platform.v1.endpoints import installations_global as platform_installations_global
from app.api.platform.v1.endpoints import session_policy as platform_session_policy
from app.api.platform.v1.endpoints import catalog_plans as platform_catalog_plans
from app.api.platform.v1.endpoints import audit_logs as platform_audit_logs
from app.api.platform.v1.endpoints import billing as platform_billing

router = APIRouter(prefix="/api/platform/v1")

router.include_router(platform_auth.router)
router.include_router(platform_companies.router)
router.include_router(platform_session_policy.router)
router.include_router(platform_subscriptions.router)
router.include_router(platform_impersonate.router)
router.include_router(stripe_webhook.router)
router.include_router(platform_analytics.router)
router.include_router(platform_config.router)
router.include_router(platform_installations.router)
router.include_router(platform_installations_global.router)
router.include_router(platform_catalog_plans.router)
router.include_router(platform_audit_logs.router)
router.include_router(platform_billing.router)
