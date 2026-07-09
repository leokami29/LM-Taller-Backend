"""Sincronizacion administrativa para SGtaller Desktop."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query

from app.schemas.sync_admin import AdminPushRequest, AdminPushResponse, AdminSyncSnapshot, SyncContext
from app.services.sync_admin import SyncAdminService, get_sync_context

router = APIRouter(prefix="/sync/admin", tags=["sync-admin"])


@router.get("/bootstrap", response_model=AdminSyncSnapshot)
def bootstrap_admin(
    installation_id: Annotated[Optional[str], Query(min_length=8, max_length=128)] = None,
    hostname: Annotated[Optional[str], Query(max_length=255)] = None,
    ctx: SyncContext = Depends(get_sync_context),
) -> AdminSyncSnapshot:
    return SyncAdminService.bootstrap(ctx, installation_id=installation_id, hostname=hostname)


@router.get("/pull", response_model=AdminSyncSnapshot)
def pull_admin(
    since: datetime | None = Query(None),
    installation_id: Annotated[Optional[str], Query(min_length=8, max_length=128)] = None,
    hostname: Annotated[Optional[str], Query(max_length=255)] = None,
    ctx: SyncContext = Depends(get_sync_context),
) -> AdminSyncSnapshot:
    return SyncAdminService.pull(
        ctx,
        since=since,
        installation_id=installation_id,
        hostname=hostname,
    )


@router.post("/push", response_model=AdminPushResponse)
def push_admin(
    payload: AdminPushRequest,
    installation_id: Annotated[Optional[str], Query(min_length=8, max_length=128)] = None,
    hostname: Annotated[Optional[str], Query(max_length=255)] = None,
    ctx: SyncContext = Depends(get_sync_context),
) -> AdminPushResponse:
    return SyncAdminService.push(
        ctx,
        payload,
        installation_id=installation_id,
        hostname=hostname,
    )
