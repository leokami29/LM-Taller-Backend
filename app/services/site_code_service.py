"""Generación de códigos cortos de sede para numeración de órdenes."""

from __future__ import annotations

import re

_CODE_RE = re.compile(r"^[A-Z0-9]{2,8}$")


def normalize_site_code(raw: str) -> str:
    code = re.sub(r"[^A-Za-z0-9]", "", (raw or "").strip()).upper()
    if len(code) < 2:
        raise ValueError("El código de sede debe tener al menos 2 caracteres alfanuméricos")
    if len(code) > 8:
        code = code[:8]
    return code


def derive_site_code(name: str, existing_codes: set[str]) -> str:
    """Deriva un código único a partir del nombre de la sede."""
    words = re.findall(r"[A-Za-z0-9]+", name or "")
    if not words:
        base = "SITE"
    elif len(words) == 1:
        base = words[0][:8].upper()
    else:
        base = "".join(w[0] for w in words[:4]).upper()
        if len(base) < 2:
            base = words[0][:8].upper()
    base = re.sub(r"[^A-Z0-9]", "", base)[:8] or "SITE"
    code = base
    n = 1
    while code in existing_codes:
        suffix = str(n)
        code = f"{base[: max(2, 8 - len(suffix))]}{suffix}"[:8]
        n += 1
    return code


def validate_site_code(code: str) -> str:
    normalized = normalize_site_code(code)
    if not _CODE_RE.match(normalized):
        raise ValueError("Código de sede inválido")
    return normalized
