"""Unit tests for address normalization.

These guard the matching pipeline. Tier 1/2 of `listing_matcher` only
work if the same physical address typed five different ways collapses
to the same string.
"""
import pytest

from app.services.address_normalizer import normalize, strip_unit, strip_zip4


class TestNormalize:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            # Casing + suffix
            ("100 N Main St",          "100 north main street"),
            ("100 north MAIN street",  "100 north main street"),
            # Punctuation
            ("100 N. Main St., Suite", "100 north main street suite"),
            # Common suffix variants
            ("5 Hwy 24",               "5 highway 24"),
            ("10 Pky Way",             "10 parkway way"),
            ("12 Pkwy",                "12 parkway"),
            ("20 Blvd Drive",          "20 boulevard drive"),
            ("30 Ave",                 "30 avenue"),
            # Directionals
            ("100 NE 14th Ave",        "100 northeast 14th avenue"),
            ("200 sw birch ln",        "200 southwest birch lane"),
            # Whitespace collapse
            ("100   Main\tStreet",     "100 main street"),
            # Empty / None passthrough
            ("",                       ""),
            (None,                     ""),
        ],
    )
    def test_normalize(self, raw: str | None, expected: str) -> None:
        assert normalize(raw) == expected

    def test_idempotent(self) -> None:
        once = normalize("100 N. Main St., Suite 200")
        twice = normalize(once)
        assert once == twice


class TestStripUnit:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("100 N Main St Apt 4B",      "100 north main street"),
            ("100 Main Street #B",        "100 main street"),
            ("100 Main St Unit 12",       "100 main street"),
            ("100 Main St Suite 200",     "100 main street"),
            ("100 Main St Ste 200",       "100 main street"),
            ("100 Main St Bldg 3",        "100 main street"),
            ("100 Main St Floor 4",       "100 main street"),
            # No unit present — pass through
            ("100 Main St",               "100 main street"),
            ("",                          ""),
        ],
    )
    def test_strip_unit(self, raw: str, expected: str) -> None:
        assert strip_unit(raw) == expected


class TestStripZip4:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("12345-6789", "12345"),
            ("12345",      "12345"),
            ("  12345  ",  "12345"),
            ("",           ""),
            (None,         ""),
        ],
    )
    def test_strip_zip4(self, raw: str | None, expected: str) -> None:
        assert strip_zip4(raw) == expected
