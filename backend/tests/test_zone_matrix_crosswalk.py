"""Unit tests for the zone_matrix_crosswalk planner.

The db-backed crosswalk function (sibling discovery + upsert) is exercised
via the admin endpoint in the manual verification steps in the plan. These
tests pin the pure planner: that city-name normalization matches what
parcels.city looks like, and that empty / blank cities don't smuggle in
junk rows.
"""
from __future__ import annotations

from app.models.zone_use_matrix import UsePermission
from app.services.zone_matrix_crosswalk import plan_crosswalk_rows


def _row(city_name: str, zone_code: str = "R-1", **overrides) -> dict:
    base = {
        "city_name": city_name,
        "zone_code": zone_code,
        "zone_name": "Single-Family Residential",
        "self_storage": UsePermission.prohibited,
        "mini_warehouse": UsePermission.prohibited,
        "light_industrial": UsePermission.prohibited,
        "luxury_garage_condo": UsePermission.prohibited,
        "citations": None,
        "confidence": 0.9,
        "notes": None,
    }
    base.update(overrides)
    return base


def test_strips_state_suffix_so_municipality_matches_parcels_city() -> None:
    """parcels.city under SLCo is normalized without the ', UT' suffix
    (zoning_system._resolve_city / _strip_state_suffix). The planner
    must produce the same form so the LATERAL join in buybox_scoring
    actually fires."""
    plans, cities = plan_crosswalk_rows([_row("Sandy, UT"), _row("Salt Lake City, UT")])
    assert {p.municipality for p in plans} == {"Sandy", "Salt Lake City"}
    assert cities == ["Salt Lake City", "Sandy"]


def test_no_state_suffix_passes_through_unchanged() -> None:
    plans, cities = plan_crosswalk_rows([_row("Draper")])
    assert plans[0].municipality == "Draper"
    assert cities == ["Draper"]


def test_blank_city_name_is_dropped() -> None:
    """A blank/whitespace city slug would land as municipality='' under
    the partial unique index — which COALESCE(municipality,'') collapses
    onto the NULL county-default slot. Better to drop it entirely than
    risk clobbering the default row."""
    plans, cities = plan_crosswalk_rows([_row(""), _row("   "), _row("Sandy")])
    assert [p.municipality for p in plans] == ["Sandy"]
    assert cities == ["Sandy"]


def test_preserves_per_zone_verdicts() -> None:
    rows = [
        _row(
            "Sandy",
            zone_code="C-2",
            self_storage=UsePermission.permitted,
            light_industrial=UsePermission.conditional,
        ),
    ]
    plans, _ = plan_crosswalk_rows(rows)
    assert plans[0].zone_code == "C-2"
    assert plans[0].self_storage == UsePermission.permitted
    assert plans[0].light_industrial == UsePermission.conditional


def test_multiple_cities_with_same_zone_code_produce_distinct_plans() -> None:
    """The whole point: 'R-1' in Sandy and 'R-1' in SLC must land as
    two separate per-city rows under the county, not collapse."""
    plans, cities = plan_crosswalk_rows([
        _row("Sandy", zone_code="R-1", self_storage=UsePermission.prohibited),
        _row("Salt Lake City", zone_code="R-1", self_storage=UsePermission.conditional),
    ])
    assert len(plans) == 2
    by_city = {p.municipality: p for p in plans}
    assert by_city["Sandy"].self_storage == UsePermission.prohibited
    assert by_city["Salt Lake City"].self_storage == UsePermission.conditional
    assert cities == ["Salt Lake City", "Sandy"]
