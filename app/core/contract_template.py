"""Validación de plantillas de formulario del portal por contrato."""

from __future__ import annotations

from typing import Any

from app.core.enums import ServiceOrderKind

ALLOWED_FIELD_TYPES = frozenset({"text", "textarea", "select", "number", "date"})


def normalize_template(template: dict[str, Any] | None) -> dict[str, Any]:
    if not template:
        return {"version": 1, "fields": []}
    version = int(template.get("version") or 1)
    fields = template.get("fields") or []
    if not isinstance(fields, list):
        raise ValueError("template_json.fields debe ser una lista")
    normalized_fields = []
    keys: set[str] = set()
    for raw in fields:
        if not isinstance(raw, dict):
            raise ValueError("Cada campo de plantilla debe ser un objeto")
        key = str(raw.get("key") or "").strip()
        if not key or key in keys:
            raise ValueError("Cada campo debe tener key única")
        keys.add(key)
        ftype = str(raw.get("type") or "text")
        if ftype not in ALLOWED_FIELD_TYPES:
            raise ValueError(f"Tipo de campo no soportado: {ftype}")
        label = str(raw.get("label") or key).strip()
        if not label:
            raise ValueError("Cada campo debe tener label")
        field: dict[str, Any] = {
            "key": key,
            "label": label,
            "type": ftype,
            "required": bool(raw.get("required")),
        }
        if ftype == "select":
            options = raw.get("options") or []
            if not isinstance(options, list) or not options:
                raise ValueError("Los campos select requieren options")
            field["options"] = [str(o) for o in options]
        normalized_fields.append(field)
    return {"version": version, "fields": normalized_fields}


def validate_submitted_against_template(
    template: dict[str, Any],
    submitted: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized = normalize_template(template)
    submitted = submitted or {}
    if not isinstance(submitted, dict):
        raise ValueError("portal_submitted_json debe ser un objeto")
    result: dict[str, Any] = {}
    for field in normalized["fields"]:
        key = field["key"]
        value = submitted.get(key)
        if field["required"] and (value is None or str(value).strip() == ""):
            raise ValueError(f"Campo obligatorio: {field['label']}")
        if value is None or str(value).strip() == "":
            continue
        if field["type"] == "select" and str(value) not in field.get("options", []):
            raise ValueError(f"Valor inválido para {field['label']}")
        result[key] = value
    extra = set(submitted.keys()) - {f["key"] for f in normalized["fields"]}
    if extra:
        raise ValueError(f"Campos no definidos en la plantilla: {', '.join(sorted(extra))}")
    return result


def validate_allowed_order_kinds(kinds: list[str]) -> list[str]:
    if not kinds:
        raise ValueError("Debe indicar al menos un tipo de orden permitido")
    valid = {k.value for k in ServiceOrderKind}
    portal_contract = {
        ServiceOrderKind.WORKSHOP_INTAKE_CONTRACT.value,
        ServiceOrderKind.FIELD_SERVICE_CONTRACT.value,
    }
    out: list[str] = []
    for k in kinds:
        if k not in valid:
            raise ValueError(f"Tipo de orden inválido: {k}")
        if k not in portal_contract:
            raise ValueError("Solo se permiten tipos de orden por contrato en el portal")
        out.append(k)
    return out
