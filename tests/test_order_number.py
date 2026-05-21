from app.core.enums import ServiceOrderKind
from app.core.order_number import format_order_number, parse_order_number


def test_format_order_number():
    assert (
        format_order_number(
            site_code="bog",
            order_kind=ServiceOrderKind.WORKSHOP_INTAKE,
            year=2026,
            sequence=1,
        )
        == "BOG-IT-2026-000001"
    )


def test_parse_order_number_roundtrip():
    raw = "MED-SCC-2027-000042"
    parsed = parse_order_number(raw)
    assert parsed is not None
    assert parsed.site_code == "MED"
    assert parsed.order_kind == ServiceOrderKind.FIELD_SERVICE_CONTRACT
    assert parsed.year == 2027
    assert parsed.sequence == 42


def test_parse_legacy_ord_returns_none():
    assert parse_order_number("ORD-000001") is None
