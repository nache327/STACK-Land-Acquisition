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
            # "Hwy 24" canonicalizes to "route 24" (highway/route are
            # interchangeable for matching purposes); see route
            # canonicalization tests for full coverage.
            ("5 Hwy 24",               "5 route 24"),
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

    @pytest.mark.parametrize(
        "raw,expected",
        [
            # Bare route phrases
            ("1150 Route 22 E",            "1150 route 22"),
            ("3070 Rt 22 W",               "3070 route 22"),
            ("672 Highway 202",            "672 route 202"),
            ("1004 Route 206 Hwy",         "1004 route 206"),
            # State / US prefixed
            ("674 US Highway 202",         "674 route 202"),
            ("351 US Hwy 22",              "351 route 22"),
            ("1165 State Route 27",        "1165 route 27"),
            ("906 Us Highway 22",          "906 route 22"),
            # Hyphenated state-route shortcuts
            ("682 US-202",                 "682 route 202"),
            ("1246 US-206",                "1246 route 206"),
            ("351 Nj-28",                  "351 route 28"),
            ("2701 NJ-27",                 "2701 route 27"),
            # Stacked prefixes / mixed forms (real CoStar mess)
            ("212 US HIGHWAY ROUTE 206",   "212 route 206"),
            ("79 N Route 206",             "79 route 206"),
            # Range collapse runs before route canonicalization, so
            # "373-377 E Route 22" becomes "373 route 22" (lower bound)
            # — covered more explicitly in test_range_and_slash_collapse.
            ("373-377 E Route 22",         "373 route 22"),
            # Routes in mid-address — shouldn't break the rest
            ("100 Route 22 Plaza",         "100 route 22 plaza"),
        ],
    )
    def test_route_canonicalization(self, raw: str, expected: str) -> None:
        assert normalize(raw) == expected

    def test_route_canonicalization_idempotent(self) -> None:
        once = normalize("1150 US Highway 22 E")
        twice = normalize(once)
        assert once == twice
        assert once == "1150 route 22"

    @pytest.mark.parametrize(
        "raw,expected",
        [
            # Address ranges — collapse to the lower house number.
            ("227-229 Adamsville Rd",       "227 adamsville road"),
            ("501-507 Omni Dr",             "501 omni drive"),
            ("10-18 Race St",               "10 race street"),
            ("176-182 Tamarack Cir",        "176 tamarack circle"),
            ("401-404 Towne Centre Dr",     "401 towne centre drive"),
            # Range combined with route phrase
            ("2041-2045 State Route 27",    "2041 route 27"),
            ("373-377 E Route 22",          "373 route 22"),
            # Dual hyphenated routes — keep the lower
            ("821-831 Route 202-206",       "821 route 202"),
            ("100 Route 202-206",           "100 route 202"),
            # Slash-separated routes — take the first.
            ("325 Route 202 / 206",         "325 route 202"),
            ("900 US Highway 202/206",      "900 route 202"),
            # Single-house addresses unchanged
            ("100 Main St",                 "100 main street"),
        ],
    )
    def test_range_and_slash_collapse(self, raw: str, expected: str) -> None:
        assert normalize(raw) == expected


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
