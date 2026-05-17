"""Políticas de sesión tenant por empresa, sede y usuario (cascada)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from app.db.models.company import Company
from app.services import platform_config_service as pcfg

SESSION_POLICIES_KEY = "session_policies"
PolicySource = Literal["global", "company", "site", "user"]
PolicyMode = Literal["inherit", "explicit"]


@dataclass(frozen=True)
class SessionPolicyEntry:
    mode: PolicyMode
    access_token_minutes: int | None = None
    refresh_token_days: int | None = None


@dataclass(frozen=True)
class ResolvedSession:
    access_token_minutes: int
    refresh_token_days: int
    source: PolicySource


@dataclass
class SessionPoliciesDocument:
    company: SessionPolicyEntry | None
    sites: dict[str, SessionPolicyEntry]
    users: dict[str, SessionPolicyEntry]

    def to_settings_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.company is not None:
            out["company"] = _entry_to_dict(self.company)
        if self.sites:
            out["sites"] = {k: _entry_to_dict(v) for k, v in self.sites.items()}
        if self.users:
            out["users"] = {k: _entry_to_dict(v) for k, v in self.users.items()}
        return out


def _global_defaults() -> tuple[int, int]:
    s = pcfg.get_session_settings()
    return s.tenant_access_token_minutes, s.tenant_refresh_token_days


def _clamp_access(minutes: int) -> int:
    return pcfg._clamp(minutes, pcfg.ACCESS_MIN_MINUTES, pcfg.ACCESS_MAX_MINUTES)


def _clamp_refresh(days: int) -> int:
    return pcfg._clamp(days, pcfg.REFRESH_MIN_DAYS, pcfg.REFRESH_MAX_DAYS)


def _entry_to_dict(entry: SessionPolicyEntry) -> dict[str, Any]:
    d: dict[str, Any] = {"mode": entry.mode}
    if entry.mode == "explicit":
        if entry.access_token_minutes is not None:
            d["access_token_minutes"] = entry.access_token_minutes
        if entry.refresh_token_days is not None:
            d["refresh_token_days"] = entry.refresh_token_days
    return d


def normalize_entry(data: dict[str, Any] | None) -> SessionPolicyEntry:
    if not data:
        return SessionPolicyEntry(mode="inherit")
    mode_raw = str(data.get("mode", "inherit")).lower()
    mode: PolicyMode = "explicit" if mode_raw == "explicit" else "inherit"
    if mode == "inherit":
        return SessionPolicyEntry(mode="inherit")
    access = data.get("access_token_minutes")
    refresh = data.get("refresh_token_days")
    g_access, g_refresh = _global_defaults()
    try:
        access_i = _clamp_access(int(access)) if access is not None else g_access
    except (TypeError, ValueError):
        access_i = g_access
    try:
        refresh_i = _clamp_refresh(int(refresh)) if refresh is not None else g_refresh
    except (TypeError, ValueError):
        refresh_i = g_refresh
    return SessionPolicyEntry(
        mode="explicit",
        access_token_minutes=access_i,
        refresh_token_days=refresh_i,
    )


def get_policies(company: Company) -> SessionPoliciesDocument:
    settings = dict(company.settings_json or {})
    raw = settings.get(SESSION_POLICIES_KEY) or {}
    if not isinstance(raw, dict):
        raw = {}
    company_raw = raw.get("company")
    company_entry = (
        normalize_entry(company_raw) if company_raw is not None else None
    )
    sites_raw = raw.get("sites") if isinstance(raw.get("sites"), dict) else {}
    users_raw = raw.get("users") if isinstance(raw.get("users"), dict) else {}
    sites = {str(k): normalize_entry(v) for k, v in sites_raw.items() if isinstance(v, dict)}
    users = {str(k): normalize_entry(v) for k, v in users_raw.items() if isinstance(v, dict)}
    return SessionPoliciesDocument(company=company_entry, sites=sites, users=users)


def _save_policies(company: Company, doc: SessionPoliciesDocument) -> None:
    settings = dict(company.settings_json or {})
    payload = doc.to_settings_dict()
    if payload:
        settings[SESSION_POLICIES_KEY] = payload
    elif SESSION_POLICIES_KEY in settings:
        del settings[SESSION_POLICIES_KEY]
    company.settings_json = settings


def set_company_policy(
    company: Company,
    entry: SessionPolicyEntry | None,
    *,
    apply_to_all_sites: bool = False,
) -> SessionPoliciesDocument:
    doc = get_policies(company)
    doc.company = entry
    if apply_to_all_sites:
        doc.sites = {}
    _save_policies(company, doc)
    return doc


def set_site_policy(
    company: Company,
    site_id: UUID,
    entry: SessionPolicyEntry,
) -> SessionPoliciesDocument:
    doc = get_policies(company)
    key = str(site_id)
    if entry.mode == "inherit":
        doc.sites.pop(key, None)
    else:
        doc.sites[key] = entry
    _save_policies(company, doc)
    return doc


def set_user_policy(
    company: Company,
    user_id: UUID,
    entry: SessionPolicyEntry,
) -> SessionPoliciesDocument:
    doc = get_policies(company)
    key = str(user_id)
    if entry.mode == "inherit":
        doc.users.pop(key, None)
    else:
        doc.users[key] = entry
    _save_policies(company, doc)
    return doc


def remove_site_policy(company: Company, site_id: UUID) -> SessionPoliciesDocument:
    return set_site_policy(company, site_id, SessionPolicyEntry(mode="inherit"))


def remove_user_policy(company: Company, user_id: UUID) -> SessionPoliciesDocument:
    return set_user_policy(company, user_id, SessionPolicyEntry(mode="inherit"))


def resolve_tenant_session(
    company: Company,
    *,
    user_id: UUID,
    site_id: UUID | None = None,
) -> ResolvedSession:
    doc = get_policies(company)
    g_access, g_refresh = _global_defaults()

    user_entry = doc.users.get(str(user_id))
    if user_entry and user_entry.mode == "explicit":
        return ResolvedSession(
            access_token_minutes=user_entry.access_token_minutes or g_access,
            refresh_token_days=user_entry.refresh_token_days or g_refresh,
            source="user",
        )

    if site_id is not None:
        site_entry = doc.sites.get(str(site_id))
        if site_entry and site_entry.mode == "explicit":
            return ResolvedSession(
                access_token_minutes=site_entry.access_token_minutes or g_access,
                refresh_token_days=site_entry.refresh_token_days or g_refresh,
                source="site",
            )

    if doc.company and doc.company.mode == "explicit":
        return ResolvedSession(
            access_token_minutes=doc.company.access_token_minutes or g_access,
            refresh_token_days=doc.company.refresh_token_days or g_refresh,
            source="company",
        )

    return ResolvedSession(
        access_token_minutes=g_access,
        refresh_token_days=g_refresh,
        source="global",
    )


def entry_display(entry: SessionPolicyEntry | None) -> dict[str, Any]:
    """Modo + valores para API (inherit sin números obligatorios)."""
    if entry is None or entry.mode == "inherit":
        return {"mode": "inherit"}
    return {
        "mode": "explicit",
        "access_token_minutes": entry.access_token_minutes,
        "refresh_token_days": entry.refresh_token_days,
    }
