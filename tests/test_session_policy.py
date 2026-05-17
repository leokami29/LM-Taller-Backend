"""Resolución en cascada de políticas de sesión tenant."""

from uuid import uuid4

import pytest

from app.db.models.company import Company
from app.services.session_policy_service import (
    ResolvedSession,
    SessionPolicyEntry,
    get_policies,
    normalize_entry,
    resolve_tenant_session,
    set_company_policy,
    set_site_policy,
    set_user_policy,
)


def _company(**kwargs) -> Company:
    c = Company(
        name="Test",
        nit_rut="900123456",
        address="Addr",
    )
    c.settings_json = kwargs.get("settings_json", {})
    return c


def test_resolve_global_only():
    company = _company()
    uid = uuid4()
    r = resolve_tenant_session(company, user_id=uid)
    assert r.source == "global"
    assert r.access_token_minutes >= 15


def test_resolve_company_explicit(monkeypatch):
    monkeypatch.setattr(
        "app.services.session_policy_service._global_defaults",
        lambda: (30, 7),
    )
    company = _company()
    set_company_policy(
        company,
        SessionPolicyEntry(mode="explicit", access_token_minutes=120, refresh_token_days=14),
    )
    r = resolve_tenant_session(company, user_id=uuid4())
    assert r.source == "company"
    assert r.access_token_minutes == 120
    assert r.refresh_token_days == 14


def test_resolve_site_override(monkeypatch):
    monkeypatch.setattr(
        "app.services.session_policy_service._global_defaults",
        lambda: (30, 7),
    )
    company = _company()
    site_id = uuid4()
    set_company_policy(
        company,
        SessionPolicyEntry(mode="explicit", access_token_minutes=120, refresh_token_days=14),
    )
    set_site_policy(
        company,
        site_id,
        SessionPolicyEntry(mode="explicit", access_token_minutes=60, refresh_token_days=3),
    )
    r = resolve_tenant_session(company, user_id=uuid4(), site_id=site_id)
    assert r.source == "site"
    assert r.access_token_minutes == 60


def test_resolve_user_beats_site(monkeypatch):
    monkeypatch.setattr(
        "app.services.session_policy_service._global_defaults",
        lambda: (30, 7),
    )
    company = _company()
    site_id = uuid4()
    user_id = uuid4()
    set_site_policy(
        company,
        site_id,
        SessionPolicyEntry(mode="explicit", access_token_minutes=60, refresh_token_days=3),
    )
    set_user_policy(
        company,
        user_id,
        SessionPolicyEntry(mode="explicit", access_token_minutes=15, refresh_token_days=1),
    )
    r = resolve_tenant_session(company, user_id=user_id, site_id=site_id)
    assert r.source == "user"
    assert r.access_token_minutes == 15


def test_apply_to_all_sites_clears_site_overrides(monkeypatch):
    monkeypatch.setattr(
        "app.services.session_policy_service._global_defaults",
        lambda: (30, 7),
    )
    company = _company()
    site_id = uuid4()
    set_site_policy(
        company,
        site_id,
        SessionPolicyEntry(mode="explicit", access_token_minutes=60, refresh_token_days=3),
    )
    assert str(site_id) in get_policies(company).sites
    set_company_policy(
        company,
        SessionPolicyEntry(mode="explicit", access_token_minutes=90, refresh_token_days=10),
        apply_to_all_sites=True,
    )
    assert get_policies(company).sites == {}


def test_normalize_inherit():
    e = normalize_entry({"mode": "inherit"})
    assert e.mode == "inherit"
