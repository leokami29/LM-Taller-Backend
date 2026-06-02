"""URLs públicas de seguimiento y resolución de tenant_slug para QR en PDF."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.config import settings
from app.db.session import catalog_session_scope

if TYPE_CHECKING:
    from app.db.models.company import Company


def resolve_tenant_slug_for_company(company_id: UUID) -> str:
    if not settings.USE_TENANT_DATABASE_ROUTING:
        return "default"
    from app.db.catalog.models import TenantRouting

    with catalog_session_scope() as catalog_db:
        row = catalog_db.query(TenantRouting).filter(TenantRouting.company_id == company_id).first()
        if row and row.slug:
            return row.slug
    return "default"


def company_public_tracking_enabled(company: Company | None) -> bool:
    if not company:
        return True
    raw: dict[str, Any] = getattr(company, "settings_json", None) or {}
    if not isinstance(raw, dict):
        return True
    flag = raw.get("public_tracking_enabled")
    if flag is None:
        return True
    return bool(flag)


def company_default_locale(company: Company | None) -> str:
    if not company:
        return "es"
    raw: dict[str, Any] = getattr(company, "settings_json", None) or {}
    if isinstance(raw, dict):
        loc = raw.get("default_locale")
        if loc in ("es", "en"):
            return str(loc)
    return "es"


def build_public_tracking_url(
    *,
    tenant_slug: str,
    tracking_code: str,
    company: Company | None = None,
    locale: str | None = None,
) -> str:
    base = (settings.PUBLIC_APP_URL or "http://localhost:3000").rstrip("/")
    loc = locale or company_default_locale(company)
    code = tracking_code.upper().strip()
    slug = tenant_slug.strip() or "default"
    return f"{base}/{loc}/seguimiento/{slug}/{code}"
