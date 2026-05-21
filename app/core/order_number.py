"""Formato y parsing del número interno de orden de servicio."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.core.enums import ServiceOrderKind

ORDER_KIND_PREFIX: dict[ServiceOrderKind, str] = {
    ServiceOrderKind.WORKSHOP_INTAKE: "IT",
    ServiceOrderKind.WORKSHOP_INTAKE_CONTRACT: "ITC",
    ServiceOrderKind.FIELD_SERVICE: "SC",
    ServiceOrderKind.FIELD_SERVICE_CONTRACT: "SCC",
}

PREFIX_TO_ORDER_KIND: dict[str, ServiceOrderKind] = {
    v: k for k, v in ORDER_KIND_PREFIX.items()
}

ORDER_NUMBER_PATTERN = re.compile(
    r"^([A-Z0-9]{2,8})-(IT|ITC|SC|SCC)-(\d{4})-(\d{6})$"
)


@dataclass(frozen=True)
class ParsedOrderNumber:
    site_code: str
    kind_prefix: str
    order_kind: ServiceOrderKind
    year: int
    sequence: int


def format_order_number(*, site_code: str, order_kind: ServiceOrderKind, year: int, sequence: int) -> str:
    prefix = ORDER_KIND_PREFIX[order_kind]
    return f"{site_code.upper()}-{prefix}-{year}-{sequence:06d}"


def parse_order_number(value: str) -> Optional[ParsedOrderNumber]:
    if not value:
        return None
    m = ORDER_NUMBER_PATTERN.match(value.strip().upper())
    if not m:
        return None
    site_code, kind_prefix, year_s, seq_s = m.groups()
    kind = PREFIX_TO_ORDER_KIND.get(kind_prefix)
    if kind is None:
        return None
    return ParsedOrderNumber(
        site_code=site_code,
        kind_prefix=kind_prefix,
        order_kind=kind,
        year=int(year_s),
        sequence=int(seq_s),
    )
