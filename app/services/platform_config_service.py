"""Configuración global de plataforma (planes, sesiones) persistida en JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings

# Backend/platform_config.json (raíz del paquete backend)
_CONFIG_PATH = Path(__file__).resolve().parents[2] / "platform_config.json"

ACCESS_MIN_MINUTES = 15
ACCESS_MAX_MINUTES = 1440
REFRESH_MIN_DAYS = 1
REFRESH_MAX_DAYS = 90

DEFAULT_PLANS: dict[str, dict[str, int]] = {
    "starter": {"monthly_price_cop": 99000, "max_active_users": 5},
    "pro": {"monthly_price_cop": 149000, "max_active_users": 15},
    "enterprise": {"monthly_price_cop": 299000, "max_active_users": 999},
}


@dataclass(frozen=True)
class SessionSettings:
    tenant_access_token_minutes: int
    tenant_refresh_token_days: int
    platform_access_token_minutes: int
    platform_refresh_token_days: int


def _default_session_dict() -> dict[str, int]:
    return {
        "tenant_access_token_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        "tenant_refresh_token_days": settings.REFRESH_TOKEN_EXPIRE_DAYS,
        "platform_access_token_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        "platform_refresh_token_days": settings.REFRESH_TOKEN_EXPIRE_DAYS,
    }


def default_config() -> dict[str, Any]:
    return {
        "plans": {k: dict(v) for k, v in DEFAULT_PLANS.items()},
        "session": _default_session_dict(),
    }


def load_config() -> dict[str, Any]:
    if _CONFIG_PATH.exists():
        with _CONFIG_PATH.open(encoding="utf-8") as f:
            raw = json.load(f)
    else:
        raw = {}
    merged = default_config()
    if isinstance(raw.get("plans"), dict):
        merged["plans"] = {**merged["plans"], **raw["plans"]}
    if isinstance(raw.get("session"), dict):
        merged["session"] = {**merged["session"], **raw["session"]}
    merged["session"] = normalize_session_dict(merged.get("session") or {})
    return merged


def save_config(config: dict[str, Any]) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def normalize_session_dict(data: dict[str, Any]) -> dict[str, int]:
    defaults = _default_session_dict()
    out: dict[str, int] = {}
    for key in defaults:
        try:
            val = int(data.get(key, defaults[key]))
        except (TypeError, ValueError):
            val = defaults[key]
        out[key] = val
    out["tenant_access_token_minutes"] = _clamp(
        out["tenant_access_token_minutes"], ACCESS_MIN_MINUTES, ACCESS_MAX_MINUTES
    )
    out["platform_access_token_minutes"] = _clamp(
        out["platform_access_token_minutes"], ACCESS_MIN_MINUTES, ACCESS_MAX_MINUTES
    )
    out["tenant_refresh_token_days"] = _clamp(
        out["tenant_refresh_token_days"], REFRESH_MIN_DAYS, REFRESH_MAX_DAYS
    )
    out["platform_refresh_token_days"] = _clamp(
        out["platform_refresh_token_days"], REFRESH_MIN_DAYS, REFRESH_MAX_DAYS
    )
    return out


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def get_session_settings() -> SessionSettings:
    session = load_config()["session"]
    return SessionSettings(
        tenant_access_token_minutes=session["tenant_access_token_minutes"],
        tenant_refresh_token_days=session["tenant_refresh_token_days"],
        platform_access_token_minutes=session["platform_access_token_minutes"],
        platform_refresh_token_days=session["platform_refresh_token_days"],
    )


def update_session_settings(payload: dict[str, int]) -> SessionSettings:
    config = load_config()
    config["session"] = normalize_session_dict({**config.get("session", {}), **payload})
    save_config(config)
    return get_session_settings()
