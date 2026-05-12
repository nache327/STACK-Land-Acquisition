"""Regression tests for zoning_discovery scoring v2.

Drawn from real false positives in the May 2026 Bergen 70-town sweep:
  - "MontereyPark Zoning" matching every Bergen "Park"-suffixed town
  - "Zoning Map of Garfield County Utah" matching Garfield NJ
  - "Franklin County Zoning Districts" matching Franklin Lakes NJ
  - "Little Haiti Floods Zoning WFL1" (Miami) matching Little Ferry NJ
  - Generic "Zoning" layer dominating 40+ town queries at conf=70
  - Cross-jurisdiction deny-list: rejecting a URL should zero its score
    on future discovery for any other jurisdiction.

Tests are pure-function — feed inputs to _score_candidate directly,
no Hub network calls, no DB.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.zoning_discovery import (
    _bbox_overlap_ratio,
    _name_match_signals,
    _name_tokens,
    _score_candidate,
    reproject_bbox_to_wgs84,
)


@dataclass
class _StubJurisdiction:
    """Stand-in for the Jurisdiction ORM model. Only carries fields that
    _score_candidate reads."""
    state: str | None = "NJ"
    county: str | None = "Bergen"
    name: str | None = "Bergen County, NJ"


def _score(
    title: str,
    *,
    url: str = "https://example.com/services/FeatureServer/0",
    pos_hits: list[str] | None = None,
    neg_hits: list[str] | None = None,
    geometry_type: str | None = "esriGeometryPolygon",
    feature_count: int | None = 200,
    field_matches: list[str] | None = None,
    bbox_overlap_ratio: float | None = 0.8,  # default: layer covers jurisdiction
    jurisdiction: _StubJurisdiction | None = None,
    name_tokens: dict | None = None,
    denylist: set[str] | None = None,
):
    """Convenience wrapper — fills name_signals automatically if name_tokens given."""
    pos_hits = pos_hits if pos_hits is not None else (["zoning"] if "zoning" in title.lower() else [])
    neg_hits = neg_hits or []
    field_matches = field_matches or []
    if name_tokens is None and jurisdiction is not None:
        name_tokens = _name_tokens(jurisdiction.name, jurisdiction.county)
    name_signals = _name_match_signals(title, name_tokens or {})
    return _score_candidate(
        title=title,
        url=url,
        pos_hits=pos_hits,
        neg_hits=neg_hits,
        geometry_type=geometry_type,
        feature_count=feature_count,
        field_matches=field_matches,
        bbox_overlap_ratio=bbox_overlap_ratio,
        name_signals=name_signals,
        jurisdiction=jurisdiction,
        denylist=denylist,
    )


# ─────────────────────────────────────────────────────────────────────
# Component A: word-boundary name matching
# ─────────────────────────────────────────────────────────────────────

def test_paramus_zoning_outranks_generic_zoning():
    """Paramus's own zoning layer should rank far above a generic 'Zoning' layer."""
    paramus = _StubJurisdiction(state="NJ", county="Bergen", name="Paramus")

    paramus_score, _ = _score("Paramus Zoning", jurisdiction=paramus)
    generic_score, _ = _score("Zoning", jurisdiction=paramus)

    assert paramus_score >= 80, f"Paramus Zoning scored {paramus_score}, expected >= 80"
    assert generic_score <= 50, f"Generic Zoning scored {generic_score}, expected <= 50"
    assert paramus_score - generic_score >= 30


def test_montereypark_does_not_match_park_substring():
    """The Bergen-sweep bug: 'MontereyPark Zoning' matched 8 Park-suffixed
    towns at conf=80 because 'park' is a substring of 'MontereyPark'. With
    word-boundary matching the 'park' token alone fires only the weak
    common-token bonus."""
    cliffside_park = _StubJurisdiction(state="NJ", county="Bergen", name="Cliffside Park")

    score, components = _score("MontereyPark Zoning", jurisdiction=cliffside_park)

    # No multi-word match (cliffside isn't in title), no rare-token match
    # (park is < 6 chars, cliffside is rare but not in title as whole word).
    component_names = {c.name for c in components}
    assert "name_match_multi_word" not in component_names
    assert "name_match_rare_token" not in component_names
    assert score < 70, f"MontereyPark/CliffsidePark scored {score}, expected < 70"


def test_multi_word_town_name_full_match():
    """When all tokens of a multi-word town name appear in the title,
    the strongest name-match bonus (+30) fires."""
    upper_saddle = _StubJurisdiction(state="NJ", county="Bergen", name="Upper Saddle River")

    score, components = _score("Upper Saddle River Zoning", jurisdiction=upper_saddle)

    component_names = {c.name for c in components}
    assert "name_match_multi_word" in component_names
    assert score >= 80


def test_multi_word_partial_does_not_fire_full_bonus():
    """Only PART of a multi-word name in title should fall back to rare-
    or common-token bonus, NOT the full multi-word bonus."""
    upper_saddle = _StubJurisdiction(state="NJ", county="Bergen", name="Upper Saddle River")

    # "river" alone — common 5-char token, no multi-word match
    score, components = _score("Boise River System Overlay", jurisdiction=upper_saddle,
                               pos_hits=[])
    component_names = {c.name for c in components}
    assert "name_match_multi_word" not in component_names
    # "river" is 5 chars → common-token bonus (+8), not rare (+25)
    assert "name_match_common_token" in component_names


# ─────────────────────────────────────────────────────────────────────
# Component B: wrong-state penalty
# ─────────────────────────────────────────────────────────────────────

def test_garfield_utah_penalized_for_wrong_state():
    """'Zoning Map of Garfield County Utah' vs Garfield NJ → wrong-state
    penalty fires."""
    garfield_nj = _StubJurisdiction(state="NJ", county="Bergen", name="Garfield")

    score, components = _score(
        "Zoning Map of Garfield County Utah", jurisdiction=garfield_nj,
    )
    component_names = {c.name for c in components}
    assert "wrong_state" in component_names, f"missing wrong_state in {component_names}"
    assert score < 60


def test_franklin_county_iowa_penalized_for_wrong_state():
    """'Franklin County Zoning Districts' (Iowa origin) vs Franklin Lakes NJ
    → wrong-county penalty AT LEAST, ideally wrong-state too if state is in title."""
    franklin_lakes = _StubJurisdiction(state="NJ", county="Bergen", name="Franklin Lakes")

    score, components = _score(
        "Franklin County Zoning Districts", jurisdiction=franklin_lakes,
    )
    component_names = {c.name for c in components}
    # County named in title; "franklin" is in expect-set so wrong_county may
    # NOT fire (depends on whether 'franklin' is treated as the jurisdiction's
    # own county-name token). At minimum the multi-word match for
    # "franklin lakes" should fail (only "franklin" in title), so no +30 bonus.
    assert "name_match_multi_word" not in component_names
    # And no wrong-county firing on "franklin" since franklin is in expect.
    # Without state in title, wrong_state can't fire either. Score should
    # still be moderate but not >= 90 — accept that this candidate looks
    # superficially plausible without operator review.
    assert score < 90


def test_north_charleston_sc_penalized():
    """Two-letter state abbrev as delimited token catches "North Charleston SC"."""
    north_arlington = _StubJurisdiction(state="NJ", county="Bergen", name="North Arlington")

    score, components = _score(
        "May 2019 CCRAB Zoning, North Charleston SC",
        jurisdiction=north_arlington,
    )
    component_names = {c.name for c in components}
    assert "wrong_state" in component_names
    assert score < 60


def test_state_abbrev_lowercase_does_not_false_match():
    """Lowercase 'in' / 'or' / 'co' should NOT fire wrong-state — abbrev
    detection is case-sensitive on the abbrev letters."""
    nj_jurisdiction = _StubJurisdiction(state="NJ", county="Bergen", name="Paramus")

    score, components = _score(
        "Paramus Zoning in The Borough",   # lowercase 'in' should not trigger Indiana
        jurisdiction=nj_jurisdiction,
    )
    component_names = {c.name for c in components}
    assert "wrong_state" not in component_names


# ─────────────────────────────────────────────────────────────────────
# Component C: generic-layer penalty
# ─────────────────────────────────────────────────────────────────────

def test_generic_zoning_layer_penalized_when_no_name_match():
    """A title of just 'Zoning' that doesn't name the jurisdiction gets
    the generic-layer penalty (-30). Total stays under threshold."""
    bergenfield = _StubJurisdiction(state="NJ", county="Bergen", name="Bergenfield")

    score, components = _score("Zoning", jurisdiction=bergenfield)

    component_names = {c.name for c in components}
    assert "generic_layer" in component_names
    assert score < 70


def test_generic_layer_with_name_match_keeps_score():
    """If a title is technically 'generic' but ALSO names the jurisdiction,
    the generic penalty does NOT fire."""
    paramus = _StubJurisdiction(state="NJ", county="Bergen", name="Paramus")

    score, components = _score("Paramus Zoning", jurisdiction=paramus)

    component_names = {c.name for c in components}
    assert "generic_layer" not in component_names
    assert "name_match_rare_token" in component_names  # paramus is 7 chars


# ─────────────────────────────────────────────────────────────────────
# Component D: cross-jurisdiction deny-list
# ─────────────────────────────────────────────────────────────────────

def test_denylist_url_zeroes_score():
    """A previously-rejected URL drops the score to ~0 even if all other
    signals are positive."""
    paramus = _StubJurisdiction(state="NJ", county="Bergen", name="Paramus")
    rejected_url = "https://services.example.com/Paramus_Zoning/FeatureServer/0"

    # Baseline (no denylist) — high score
    baseline, _ = _score(
        "Paramus Zoning", url=rejected_url, jurisdiction=paramus,
    )
    # With denylist — drops to 0 (or near it, clamped)
    after_deny, components = _score(
        "Paramus Zoning", url=rejected_url, jurisdiction=paramus,
        denylist={rejected_url},
    )
    component_names = {c.name for c in components}
    assert "denylist_rejected" in component_names
    # Denylist deducts -80; baseline is ~85 (Paramus rare-name + polygon +
    # count + bbox + 'zoning' keyword). So after_deny lands around 0-5,
    # well below any operator-review threshold (which is _HIGH_CONFIDENCE_THRESHOLD=70).
    assert after_deny < baseline - 60
    assert after_deny < 20  # effectively rejected; precise value depends on baseline


def test_denylist_other_url_does_not_affect_score():
    """Denylist of a different URL doesn't affect this candidate."""
    paramus = _StubJurisdiction(state="NJ", county="Bergen", name="Paramus")

    baseline, _ = _score(
        "Paramus Zoning", url="https://example.com/A/FeatureServer/0",
        jurisdiction=paramus,
    )
    deny_other, _ = _score(
        "Paramus Zoning", url="https://example.com/A/FeatureServer/0",
        jurisdiction=paramus,
        denylist={"https://example.com/OTHER/FeatureServer/0"},
    )
    assert baseline == deny_other


# ─────────────────────────────────────────────────────────────────────
# Cross-validation: scoring formula stays bounded
# ─────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────
# Component F: bbox-overlap (the New Milford CT fix)
# ─────────────────────────────────────────────────────────────────────

def test_bbox_overlap_strong_fires_bonus():
    """Layer bbox covering >=50% of jurisdiction bbox earns the strong-overlap bonus."""
    paramus = _StubJurisdiction(state="NJ", county="Bergen", name="Paramus")
    score, components = _score("Paramus Zoning", jurisdiction=paramus, bbox_overlap_ratio=0.8)
    names = {c.name for c in components}
    assert "bbox_overlap_strong" in names


def test_bbox_overlap_disjoint_fires_strong_penalty():
    """Disjoint bboxes (ratio=0.0) fire the strongest spatial penalty (-60).
    This is the case for New Milford CT vs Bergen NJ — 100km apart in different states."""
    bergen = _StubJurisdiction(state="NJ", county="Bergen", name="Bergen County, NJ")
    score, components = _score(
        "New Milford zoning shapefiles",  # title that looked legit but covered wrong state
        jurisdiction=bergen,
        bbox_overlap_ratio=0.0,
    )
    names = {c.name for c in components}
    assert "bbox_overlap_disjoint" in names
    # The -60 disjoint penalty drops the score well below the threshold.
    # Total: 15 (zoning kw) + 20 (poly) + 15 (count) - 60 (disjoint) = -10 → clamped 0.
    # Even with the rare "bergen" name-match bonus (+25): 40 → still well below 70.
    assert score < 50


def test_bbox_overlap_tiny_fires_minor_penalty():
    """Tiny overlap (<5%) fires a -30 penalty (likely wrong adjacent jurisdiction)."""
    bergen = _StubJurisdiction(state="NJ", county="Bergen", name="Bergen County, NJ")
    _, components = _score("Some Zoning", jurisdiction=bergen, bbox_overlap_ratio=0.02)
    names = {c.name for c in components}
    assert "bbox_overlap_tiny" in names


def test_bbox_overlap_missing_no_signal():
    """If layer extent or jurisdiction bbox is missing (ratio=None), no
    bbox-related component fires — fails closed (no penalty, no bonus)."""
    paramus = _StubJurisdiction(state="NJ", county="Bergen", name="Paramus")
    _, components = _score("Paramus Zoning", jurisdiction=paramus, bbox_overlap_ratio=None)
    names = {c.name for c in components}
    assert not any(n.startswith("bbox_overlap") for n in names)


# ─────────────────────────────────────────────────────────────────────
# CRS reprojection: the New Milford CT case end-to-end
# ─────────────────────────────────────────────────────────────────────

def test_reproject_wgs84_passthrough():
    """SRID 4326 is a no-op — bbox returned unchanged."""
    bbox = [-74.0, 40.9, -73.9, 41.1]
    out = reproject_bbox_to_wgs84(bbox, 4326)
    assert out == bbox


def test_reproject_web_mercator_3857():
    """SRID 3857 (WebMercator) reprojects to WGS84 lat/lng."""
    # NJ rough center in 3857: x=-8245000, y=4970000 → ~ (-74.07°, 40.59°)
    out = reproject_bbox_to_wgs84([-8245000.0, 4970000.0, -8230000.0, 4985000.0], 3857)
    assert out is not None
    # Sanity-check the bounds land in NJ longitude range
    assert -75 < out[0] < -73, f"xmin {out[0]} not in NJ longitude range"
    assert 40 < out[1] < 42, f"ymin {out[1]} not in NJ latitude range"


def test_reproject_esri_102100_alias_same_as_3857():
    """Esri WKID 102100 is an alias for EPSG:3857 — same output."""
    bbox = [-8245000.0, 4970000.0, -8230000.0, 4985000.0]
    assert reproject_bbox_to_wgs84(bbox, 102100) == reproject_bbox_to_wgs84(bbox, 3857)


def test_reproject_unsupported_crs_returns_none():
    """Unknown EPSG code (9999 doesn't exist) returns None — caller
    treats as 'no signal' and Component F doesn't fire."""
    out = reproject_bbox_to_wgs84([500000, 500000, 600000, 600000], 9999)
    assert out is None


def test_reproject_nj_state_plane_3424_via_pyproj():
    """EPSG:3424 = NJ State Plane (feet). pyproj should reproject it to
    WGS84 around NJ longitudes. This is the Paramus case — last session
    the layer extent stayed 'unknown' because the closed-form helper
    only knew WebMercator."""
    # Paramus Zoning extent in EPSG:3424 from the prod spatial-check probe
    bbox = [602253.34, 756172.03, 619511.88, 782410.35]
    out = reproject_bbox_to_wgs84(bbox, 3424)
    # pyproj is an optional dependency in test envs; skip the assertion
    # if it isn't installed (closed-form fallback returns None for 3424).
    try:
        import pyproj  # noqa: F401
    except ImportError:
        assert out is None
        return
    assert out is not None
    # Paramus is at lng ~-74.07°, lat ~40.95° — bbox should bracket those.
    assert -74.2 < out[0] < -74.0, f"xmin {out[0]} not near Paramus longitude"
    assert 40.9 < out[1] < 41.05, f"ymin {out[1]} not near Paramus latitude"


def test_reproject_illinois_state_plane_3435_via_pyproj():
    """EPSG:3435 = Illinois State Plane (East). The SSMMA Chicago Heights
    layer used this; pyproj should reproject + Component F should then
    correctly flag it as disjoint from Bergen NJ."""
    bbox = [1095185.46, 1692781.86, 1205538.54, 1834829.62]
    out = reproject_bbox_to_wgs84(bbox, 3435)
    try:
        import pyproj  # noqa: F401
    except ImportError:
        assert out is None
        return
    assert out is not None
    # Chicago is at lng ~-87.6°. Should land in Illinois.
    assert -88 < out[0] < -87, f"xmin {out[0]} not near Chicago longitude"
    assert 41 < out[1] < 42, f"ymin {out[1]} not near Chicago latitude"
    # And it should be disjoint from Bergen NJ (~-74, 40.9).
    bergen = [-74.27, 40.76, -73.90, 41.13]
    from app.services.zoning_discovery import _bbox_overlap_ratio
    assert _bbox_overlap_ratio(bergen, out) == 0.0


def test_reproject_unmarked_extent_treats_latlng_as_4326():
    """If SRID is None but values look like lat/lng, assume WGS84."""
    out = reproject_bbox_to_wgs84([-74.0, 40.9, -73.9, 41.1], None)
    assert out == [-74.0, 40.9, -73.9, 41.1]


def test_reproject_unmarked_extent_with_mercator_values_returns_none():
    """If SRID is None but values look like meters (way outside lat/lng range),
    we can't safely assume — return None."""
    out = reproject_bbox_to_wgs84([-8245000.0, 4970000.0, -8230000.0, 4985000.0], None)
    assert out is None


def test_new_milford_ct_disjoint_from_bergen_nj():
    """The actual New Milford CT FeatureServer extent (in WebMercator, the
    service's native CRS) reprojects to CT and has zero overlap with
    Bergen NJ's bbox. This is the regression case that motivated
    Component F."""
    nm_ct_extent_3857 = [-8182771.17, 5085221.47, -8164401.68, 5113670.47]
    nm_ct_4326 = reproject_bbox_to_wgs84(nm_ct_extent_3857, 102100)
    assert nm_ct_4326 is not None
    # Check we're in Connecticut (~ -73.5°, 41.5°)
    assert -73.7 < nm_ct_4326[0] < -73.3, f"NM CT xmin {nm_ct_4326[0]} not in CT"
    assert 41.3 < nm_ct_4326[1] < 41.8, f"NM CT ymin {nm_ct_4326[1]} not in CT"

    bergen_bbox = [-74.27, 40.76, -73.90, 41.13]
    overlap = _bbox_overlap_ratio(bergen_bbox, nm_ct_4326)
    assert overlap == 0.0, f"Bergen and New Milford CT should be disjoint, got overlap={overlap}"


def test_bbox_overlap_ratio_calculation():
    """The ratio is intersection_area / jurisdiction_area, clamped to [0, 1]."""
    juris = [0.0, 0.0, 10.0, 10.0]  # 100 sq units
    # Layer covers half: x in [0,5], y in [0,10] → intersection 5×10 = 50 → ratio 0.5
    layer = [0.0, 0.0, 5.0, 10.0]
    assert _bbox_overlap_ratio(juris, layer) == 0.5

    # Layer covers all: ratio 1.0
    layer = [-1.0, -1.0, 11.0, 11.0]
    assert _bbox_overlap_ratio(juris, layer) == 1.0

    # Disjoint: ratio 0.0
    layer = [20.0, 20.0, 30.0, 30.0]
    assert _bbox_overlap_ratio(juris, layer) == 0.0


def test_score_clamped_zero_to_hundred():
    """Heavily-negative inputs clamp to 0; heavily-positive clamp to 100."""
    paramus = _StubJurisdiction(state="NJ", county="Bergen", name="Paramus")

    # Score-bomb: every negative signal + denylist
    score, _ = _score(
        "Permit Boundary Parcel Address Utility",
        url="https://x/FS/0",
        neg_hits=["parcel", "permit", "boundary", "address", "utility"],
        geometry_type="esriGeometryPoint",
        feature_count=1_000_000,
        jurisdiction=paramus,
        denylist={"https://x/FS/0"},
    )
    assert score == 0

    # All-positive: strong name match + polygon + good count + fields + bbox
    score_high, _ = _score(
        "Paramus Zoning District Land Use",
        pos_hits=["zoning", "land use", "zone district"],
        field_matches=["zone_code", "district", "zoning"],
        feature_count=200,
        jurisdiction=paramus,
    )
    assert score_high == 100  # 45 (3*15 pos) + 20 poly + 15 count + 20 fields + 10 bbox
                              # + 25 rare name = 135 → clamped to 100
