from __future__ import annotations

from datetime import datetime

from app.config import settings
from app.db.models.company import Company
from app.db.session import catalog_session_scope
from app.schemas.sync_admin import AdminPushRequest, AdminPushResponse, AdminSyncSnapshot, SyncContext
from app.services.installation_service import record_installation_sync
from app.services.sync_admin.context import ensure_subscription_allows_push, ensure_subscription_allows_sync
from app.services.sync_admin.push import apply_mutation
from app.services.sync_admin.snapshot import attach_license, build_snapshot, filter_snapshot_since
from app.services.tenant_config_events import (
    TenantConfigReason,
    bump_company_config_revision,
    notify_company_config_changed,
)


class SyncAdminService:
    @staticmethod
    def bootstrap(
        ctx: SyncContext,
        *,
        installation_id: str | None = None,
        hostname: str | None = None,
    ) -> AdminSyncSnapshot:
        ensure_subscription_allows_sync(ctx)
        snap = build_snapshot(ctx)
        return attach_license(ctx, snap, installation_id=installation_id, hostname=hostname)

    @staticmethod
    def pull(
        ctx: SyncContext,
        *,
        since: datetime | None = None,
        installation_id: str | None = None,
        hostname: str | None = None,
    ) -> AdminSyncSnapshot:
        ensure_subscription_allows_sync(ctx)
        snap = build_snapshot(ctx)
        if since is not None:
            snap = filter_snapshot_since(snap, since)
        return attach_license(ctx, snap, installation_id=installation_id, hostname=hostname)

    @staticmethod
    def push(
        ctx: SyncContext,
        payload: AdminPushRequest,
        *,
        installation_id: str | None = None,
        hostname: str | None = None,
    ) -> AdminPushResponse:
        ensure_subscription_allows_push(ctx)
        results = [apply_mutation(ctx, mutation) for mutation in payload.mutations]
        ctx.db.commit()
        if any(r.status == "applied" for r in results):
            company = ctx.db.query(Company).filter(Company.id == ctx.company_id).first()
            if company:
                revision = bump_company_config_revision(company)
                ctx.db.add(company)
                ctx.db.commit()
                notify_company_config_changed(ctx.company_id, TenantConfigReason.COMPANY_STATUS, revision)
            if installation_id and settings.USE_TENANT_DATABASE_ROUTING:
                company_for_sync = ctx.db.query(Company).filter(Company.id == ctx.company_id).first()
                if company_for_sync:
                    with catalog_session_scope() as catalog_db:
                        record_installation_sync(
                            catalog_db,
                            company_id=ctx.company_id,
                            installation_id=installation_id,
                            hostname=hostname,
                            plan_code=company_for_sync.plan.value,
                        )
                        catalog_db.commit()
        return AdminPushResponse(results=results, cursor=datetime.utcnow().isoformat())
