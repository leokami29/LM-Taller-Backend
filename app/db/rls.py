"""Contexto RLS Postgres (set_config) por request."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import SecurityUtils


def apply_rls_session_context(db: Session, authorization: str | None) -> None:
    """Resetea y aplica variables de sesión usadas por políticas RLS."""
    db.execute(text("SELECT set_config('app.platform_access', 'false', true)"))
    db.execute(text("SELECT set_config('app.tenant_company_id', '', true)"))
    if not authorization or not authorization.lower().startswith("bearer "):
        return
    token = authorization[7:].strip()
    payload = SecurityUtils.decode_token(token)
    if not payload:
        return
    if payload.get("token_use") and payload.get("token_use") != "access":
        return
    typ = payload.get("typ")
    if typ == "platform":
        db.execute(text("SELECT set_config('app.platform_access', 'true', true)"))
        act = payload.get("act_as_company_id")
        if act:
            db.execute(
                text("SELECT set_config('app.tenant_company_id', :cid, true)"),
                {"cid": str(act)},
            )
        return
    if typ in (None, "tenant"):
        cid = payload.get("company_id")
        if cid:
            db.execute(
                text("SELECT set_config('app.tenant_company_id', :cid, true)"),
                {"cid": str(cid)},
            )
