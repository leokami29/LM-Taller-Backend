import pytest

from app.core.rut import (
    clean_rut,
    format_rut_canonical,
    format_rut_display,
    is_valid_chilean_rut,
    validate_rut_field,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("11.111.111-1", True),
        ("11111111-1", True),
        ("12.345.678-5", True),
        ("123456785", True),
        ("12345678-0", False),
        ("", False),
        ("abc", False),
    ],
)
def test_is_valid_chilean_rut(raw: str, expected: bool) -> None:
    assert is_valid_chilean_rut(raw) is expected


def test_clean_and_format() -> None:
    assert clean_rut("12.345.678-k") == "12345678K"
    assert format_rut_canonical("12.345.678-5") == "12345678-5"
    assert format_rut_display("123456785") == "12.345.678-5"


def test_validate_rut_field_raises() -> None:
    with pytest.raises(ValueError, match="inválido"):
        validate_rut_field("12345678-0")
