"""Contadores ligeros para observabilidad de resolución de tenant (sin dependencias externas)."""

from __future__ import annotations

import logging
from threading import Lock
from typing import Any

logger = logging.getLogger("sgtaller.tenancy.metrics")

_lock = Lock()
_counts: dict[str, int] = {
    "resolve_by_company_total": 0,
    "resolve_by_company_cache_hit": 0,
    "resolve_by_company_source_env": 0,
    "resolve_by_company_source_catalog": 0,
    "resolve_by_slug_total": 0,
    "resolve_by_slug_cache_hit": 0,
    "resolve_errors": 0,
    "tenant_engine_evictions": 0,
}


def bump(key: str, delta: int = 1) -> None:
    with _lock:
        _counts[key] = _counts.get(key, 0) + delta


def record_engine_eviction() -> None:
    bump("tenant_engine_evictions", 1)


def snapshot() -> dict[str, int]:
    with _lock:
        return dict(_counts)


def log_resolve_event(
    *,
    method: str,
    company_id: str | None,
    cache_hit: bool,
    source: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """Log estructurado sin PII de credenciales (solo UUID y fuente)."""
    payload: dict[str, Any] = {
        "event": "tenant_resolve",
        "method": method,
        "company_id": company_id,
        "cache_hit": cache_hit,
        "source": source,
    }
    if extra:
        payload.update(extra)
    logger.debug("%s", payload)
