"""Validación y formato de RUT chileno (módulo 11)."""

from __future__ import annotations

import re

_RUT_CLEAN = re.compile(r"[^0-9kK]")


def clean_rut(value: str) -> str:
    return _RUT_CLEAN.sub("", value.strip()).upper()


def _verification_digit(body: str) -> str:
    total = 0
    factor = 2
    for digit in reversed(body):
        total += int(digit) * factor
        factor = 2 if factor == 7 else factor + 1
    remainder = 11 - (total % 11)
    if remainder == 11:
        return "0"
    if remainder == 10:
        return "K"
    return str(remainder)


def is_valid_chilean_rut(value: str | None) -> bool:
    if not value or not str(value).strip():
        return False
    cleaned = clean_rut(str(value))
    if len(cleaned) < 2:
        return False
    body, dv = cleaned[:-1], cleaned[-1]
    if not body.isdigit() or len(body) > 8:
        return False
    if dv not in "0123456789K":
        return False
    return _verification_digit(body) == dv


def format_rut_canonical(value: str) -> str:
    """Forma canónica sin puntos: 12345678-K"""
    cleaned = clean_rut(value)
    if len(cleaned) < 2:
        return cleaned
    return f"{cleaned[:-1]}-{cleaned[-1]}"


def format_rut_display(value: str) -> str:
    """Forma legible: 12.345.678-K"""
    cleaned = clean_rut(value)
    if len(cleaned) < 2:
        return value.strip()
    body, dv = cleaned[:-1], cleaned[-1]
    rev = list(reversed(body))
    parts: list[str] = []
    while rev:
        parts.append("".join(reversed(rev[:3])))
        rev = rev[3:]
    formatted_body = ".".join(reversed(parts))
    return f"{formatted_body}-{dv}"


def validate_rut_field(value: str | None, *, required: bool = False) -> str | None:
    if value is None or not str(value).strip():
        if required:
            raise ValueError("RUT requerido")
        return None
    if not is_valid_chilean_rut(value):
        raise ValueError("RUT inválido (dígito verificador incorrecto)")
    return format_rut_canonical(value)
