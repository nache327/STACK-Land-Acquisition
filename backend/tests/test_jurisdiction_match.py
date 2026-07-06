"""
Regression tests for _match_jurisdiction (Tier 1.3): exact-match-first plus a
state-gated substring fallback, so a same-named jurisdiction in the wrong state
can never be resolved (catch #46 sibling — the registry-lookup fix).
"""
from __future__ import annotations

from app.services.pipeline import KNOWN_JURISDICTIONS, _match_jurisdiction


def test_exact_key_match():
    assert _match_jurisdiction("montgomery county, pa").name == "Montgomery County, PA"


def test_state_suffix_still_routes():
    m = _match_jurisdiction("Draper, UT")
    assert m is not None and m.state == "UT"


def test_never_crosses_state_lines():
    """A state-suffixed input must resolve to that state or to nothing — never
    to a same-named config in a different state."""
    m = _match_jurisdiction("Montgomery County, MD")
    assert m is None or m.state == "MD"


def test_wrong_state_same_name_is_rejected():
    """Synthesize the classic failure: an input whose town name substring-hits a
    registry key but whose state hint disagrees must not match that key."""
    # Pick any PA registry entry and feed its town with an NJ suffix.
    pa = next(c for c in KNOWN_JURISDICTIONS.values() if c.state == "PA")
    town = pa.name.split(" County")[0].split(",")[0]  # e.g. "Montgomery"
    m = _match_jurisdiction(f"{town} Township, NJ")
    assert m is None or m.state == "NJ"


def test_empty_input():
    assert _match_jurisdiction("") is None
    assert _match_jurisdiction("   ") is None
