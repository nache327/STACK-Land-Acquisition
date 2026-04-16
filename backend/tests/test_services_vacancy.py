"""Unit tests for vacancy detection helpers — no database required."""
from app.services.vacancy import (
    VACANT_LANDUSE_CODES,
    is_vacant_by_improvement_value,
    is_vacant_by_landuse,
)


def test_improvement_value_zero_is_vacant() -> None:
    assert is_vacant_by_improvement_value(0) is True
    assert is_vacant_by_improvement_value(0.0) is True


def test_improvement_value_positive_is_not_vacant() -> None:
    assert is_vacant_by_improvement_value(100_000) is False


def test_improvement_value_none_is_unknown() -> None:
    assert is_vacant_by_improvement_value(None) is None


def test_vacant_landuse_codes_recognised() -> None:
    for code in ["vacant land", "VACANT LAND", "Vacant Res", "vac comm"]:
        assert is_vacant_by_landuse(code) is True, f"Expected True for {code!r}"


def test_non_vacant_landuse_code() -> None:
    assert is_vacant_by_landuse("single family residential") is False


def test_none_landuse_code() -> None:
    assert is_vacant_by_landuse(None) is None


def test_vacant_landuse_codes_set_not_empty() -> None:
    assert len(VACANT_LANDUSE_CODES) > 0
