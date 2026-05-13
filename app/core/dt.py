"""Fechas UTC con zona horaria explícita (sustituye datetime.utcnow, deprecado en Python 3.12+)."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
