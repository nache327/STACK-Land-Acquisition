"""Unit test for the state-suffix-aware jurisdiction-name normalization in
POST /api/jobs.

The pre-fix code split user input on ',' and lowercased the head, then
compared the result against LOWER(jurisdictions.name). With stored names
like "Salt Lake County, UT", the comparison was "salt lake county" vs
"salt lake county, ut" — never matched, so every repeat search spawned
a fresh ingest of an already-cached county. This test pins the fix:
inputs with and without state suffix all collapse to the same key.
"""
from __future__ import annotations

from app.services.jurisdiction_match import strip_state_suffix_lower


def test_lowercases_and_strips_two_letter_state_code() -> None:
    assert strip_state_suffix_lower("Salt Lake County, UT") == "salt lake county"
    assert strip_state_suffix_lower("salt lake county, ut") == "salt lake county"
    assert strip_state_suffix_lower("Draper City, UT") == "draper city"


def test_input_without_state_suffix_passes_through() -> None:
    assert strip_state_suffix_lower("Salt Lake County") == "salt lake county"
    assert strip_state_suffix_lower("Provo") == "provo"


def test_trims_surrounding_whitespace() -> None:
    assert strip_state_suffix_lower("  Salt Lake County, UT  ") == "salt lake county"
    assert strip_state_suffix_lower("Draper City , UT") == "draper city"


def test_does_not_strip_when_tail_is_not_a_state_code() -> None:
    """', Borough' etc. is part of the place name, not a state code, so
    leave it alone. Two-letter heuristic protects against this."""
    assert strip_state_suffix_lower("Brooklyn, NY 11201") == "brooklyn, ny 11201"
    assert strip_state_suffix_lower("Manhattan, Borough") == "manhattan, borough"


def test_handles_multi_comma_input() -> None:
    """rsplit on the LAST comma — handles things like
    'Salt Lake City, Salt Lake County, UT' by stripping only the trailing ', UT'."""
    assert (
        strip_state_suffix_lower("Salt Lake City, Salt Lake County, UT")
        == "salt lake city, salt lake county"
    )
