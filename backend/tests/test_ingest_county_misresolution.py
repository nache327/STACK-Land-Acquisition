"""Guards for the county-ingest mis-resolution class (Mercer→Ocean, twice).

Two independent defects let "Mercer County, NJ" ingest OCEAN County's 422k
parcels under state='NE':

  1. STATE: the geocoder's Region arrives as a full state name and the old
     fallback truncated it — "New Jersey"[:2].upper() == "NE" — and the geocoder
     value was preferred over the ", NJ" the user literally typed.
  2. LAYER: ArcGIS Hub candidates were ranked purely by len(title), with only an
     *intersects* bbox filter, so a neighboring county's layer titled "Parcels"
     beat everything, and nothing ever verified the chosen layer's extent.

Plus the backstop: the parcels upsert conflicts on (jurisdiction_id, apn), so a
wrong-county ingest NEVER conflicts — it silently duplicates a county. The APN
collision gate is the source-agnostic invariant: the same physical county's
parcels must never land under two jurisdiction rows.
"""
from __future__ import annotations

import pytest

from app.services.arcgis_discovery import (
    GeocodedPlace,
    _extent_contains_point,
    _name_tokens,
    _state_from_geocoder,
)
from app.services.ingestion import evaluate_apn_collision
from app.services.pipeline import _match_jurisdiction


# ── 1. State derivation ──────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("region", "address", "want"),
    [
        # The bug: full state names must map via the states table, never truncate.
        ("New Jersey", "MERCER COUNTY, NEW JERSEY", "NJ"),
        ("New York", "", "NY"),
        ("New Mexico", "", "NM"),
        ("New Hampshire", "", "NH"),
        ("Nebraska", "", "NE"),          # the one case where NE is CORRECT
        ("North Carolina", "", "NC"),
        # Already a 2-letter code → passthrough.
        ("NJ", "", "NJ"),
        ("nj", "", "NJ"),
        # Region unusable → the address's ", XX" code.
        ("", "188 BOUNDARY RD, MARLBORO, NJ, 07746", "NJ"),
        # Nothing derivable → EMPTY, visibly wrong beats confidently wrong.
        ("", "", ""),
        ("Atlantis", "", ""),
    ],
)
def test_state_from_geocoder_never_truncates(region, address, want):
    assert _state_from_geocoder(region, address) == want


def test_the_exact_mercer_failure_shape():
    """The literal prod inputs that produced state='NE'."""
    got = _state_from_geocoder("New Jersey", "MERCER COUNTY, NEW JERSEY")
    assert got == "NJ", (
        f"got {got!r} — 'New Jersey' collapsing to 'NE' is the truncation bug "
        f"that mislabelled Mercer/Morris/Paterson/Elizabeth rows in prod"
    )


# ── 2. Registry: NJ counties never reach live discovery ─────────────────────

@pytest.mark.parametrize(
    ("query", "county"),
    [
        ("Mercer County, NJ", "MERCER"),
        ("mercer county", "MERCER"),
        ("Trenton, NJ", "MERCER"),
        ("Princeton, NJ", "MERCER"),
        ("Camden County, NJ", "CAMDEN"),
        ("Gloucester County, NJ", "GLOUCESTER"),
        ("Atlantic County, NJ", "ATLANTIC"),
        ("Cumberland County, NJ", "CUMBERLAND"),
        ("Salem County, NJ", "SALEM"),
        ("Cape May County, NJ", "CAPE MAY"),
        ("Sussex County, NJ", "SUSSEX"),
        ("Warren County, NJ", "WARREN"),
    ],
)
def test_every_nj_county_resolves_from_the_registry(query, county):
    cfg = _match_jurisdiction(query)
    assert cfg is not None, f"{query!r} fell through to live discovery"
    assert cfg.state == "NJ"
    assert cfg.where_clause == f"COUNTY='{county}'"
    # Registry configs are vetted — the collision gate must run warn-only.
    assert cfg.discovered_live is False


# ── 3. Hub layer gate ────────────────────────────────────────────────────────

# Ocean County NJ's real extent vs Trenton — the observed wrong-layer pairing.
_OCEAN_EXTENT = {
    "extent": {
        "xmin": -74.552, "ymin": 39.504, "xmax": -74.032, "ymax": 40.172,
        "spatialReference": {"wkid": 4326},
    }
}
_TRENTON = (-74.7597, 40.2206)


def test_extent_gate_rejects_the_observed_wrong_county():
    assert _extent_contains_point(_OCEAN_EXTENT, *_TRENTON) is False


def test_extent_gate_accepts_the_right_county():
    mercerish = {
        "extent": {
            "xmin": -74.95, "ymin": 40.13, "xmax": -74.42, "ymax": 40.45,
            "spatialReference": {"wkid": 4326},
        }
    }
    assert _extent_contains_point(mercerish, *_TRENTON) is True


def test_extent_gate_fails_open_on_indeterminate_metadata():
    """A publisher's missing/corrupt extent must not break healthy discovery."""
    assert _extent_contains_point({}, *_TRENTON) is True
    assert _extent_contains_point({"extent": "not-a-dict"}, *_TRENTON) is True
    assert _extent_contains_point(
        {"extent": {"xmin": 5, "ymin": 5, "xmax": 1, "ymax": 1}}, *_TRENTON
    ) is True  # inverted extent = corrupt
    # WKID claims WGS84 but values are Web-Mercator metres → implausible, fail open
    assert _extent_contains_point(
        {"extent": {"xmin": -8_300_000, "ymin": 4_800_000,
                    "xmax": -8_200_000, "ymax": 4_900_000,
                    "spatialReference": {"wkid": 4326}}},
        *_TRENTON,
    ) is True


def test_extent_gate_handles_web_mercator():
    # Ocean County's extent in EPSG:3857 metres — must still reject Trenton.
    ocean_3857 = {
        "extent": {
            "xmin": -8299064.0, "ymin": 4784064.0,
            "xmax": -8241178.0, "ymax": 4881669.0,
            "spatialReference": {"wkid": 102100, "latestWkid": 3857},
        }
    }
    assert _extent_contains_point(ocean_3857, *_TRENTON) is False


def test_name_tokens_extract_identity_words_only():
    geo = GeocodedPlace(
        city="Trenton", state="NJ", county="Mercer County",
        lat=40.22, lon=-74.76, bbox=[-75, 40, -74.5, 40.5],
    )
    tokens = _name_tokens("Mercer County, NJ", geo)
    assert "mercer" in tokens
    assert "trenton" in tokens
    assert "county" not in tokens      # generic locality words carry no identity


# ── 4. APN collision gate (pure decision function) ──────────────────────────

def _collider(hits, state="NJ", name="Ocean County, NJ"):
    return {"jurisdiction_id": "b26af20d", "name": name, "state": state, "hits": hits}


def test_gate_aborts_the_mercer_ocean_signature():
    """~100% same-state overlap from a live-discovered source → abort."""
    verdict, info = evaluate_apn_collision(
        [_collider(998)], sampled=1000, target_state="NJ", policy="strict"
    )
    assert verdict == "abort"
    assert info is not None and info["name"] == "Ocean County, NJ"
    assert info["fraction"] > 0.99


def test_gate_passes_below_threshold():
    verdict, _ = evaluate_apn_collision(
        [_collider(400)], sampled=1000, target_state="NJ", policy="strict"
    )
    assert verdict == "ok"


def test_gate_warns_not_aborts_cross_state():
    """Generic APN formats legitimately collide across states."""
    verdict, info = evaluate_apn_collision(
        [_collider(900, state="AZ", name="Maricopa County, AZ")],
        sampled=1000, target_state="NJ", policy="strict",
    )
    assert verdict == "warn"
    assert info is not None and info["same_state"] is False


def test_gate_warns_not_aborts_for_vetted_sources():
    """Deliberate double coverage (Draper within Salt Lake County) must not abort."""
    verdict, _ = evaluate_apn_collision(
        [_collider(900, state="UT", name="Salt Lake County, UT")],
        sampled=1000, target_state="UT", policy="warn",
    )
    assert verdict == "warn"


def test_gate_stays_silent_below_min_sample():
    """A tiny municipality cannot support a confident verdict."""
    verdict, _ = evaluate_apn_collision(
        [_collider(150)], sampled=150, target_state="NJ", policy="strict"
    )
    assert verdict == "ok"


def test_gate_groups_per_collider_not_globally():
    """County umbrella vs several carve-outs: each stays below threshold.

    Summing across colliders (the wrong design) would read 60% and abort;
    per-collider grouping keeps the max at 30% and passes. This is the Mount
    Laurel false-positive class.
    """
    colliders = [
        _collider(300, name="Mount Laurel, NJ"),
        _collider(200, name="Evesham, NJ"),
        _collider(100, name="Moorestown, NJ"),
    ]
    verdict, _ = evaluate_apn_collision(
        colliders, sampled=1000, target_state="NJ", policy="strict"
    )
    assert verdict == "ok"


def test_gate_handles_no_colliders():
    verdict, info = evaluate_apn_collision(
        [], sampled=1000, target_state="NJ", policy="strict"
    )
    assert verdict == "ok" and info is None


@pytest.mark.asyncio
async def test_cancel_check_aborts_before_upsert(monkeypatch) -> None:
    """A cancellation detected at the last line must abort BEFORE the bulk
    upsert writes anything — the 2026-08-10 zombie committed 422k rows of a
    cancelled job because every earlier checkpoint shared the worker's session."""
    import asyncio as _asyncio
    import uuid as _uuid

    import geopandas as gpd
    from shapely.geometry import Polygon

    from app.services import ingestion as ing

    upserted: list[int] = []

    async def fake_upsert(rows, cb, force=False):
        upserted.append(len(rows))
        return len(rows)

    async def fake_gate(*a, **k):
        return None

    async def fake_scalar(*a, **k):
        return "NJ"

    class _DB:
        scalar = staticmethod(fake_scalar)

    monkeypatch.setattr(ing, "_copy_upsert_parcels", fake_upsert)
    monkeypatch.setattr(ing, "_apn_collision_gate", fake_gate)

    poly = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
    gdf = gpd.GeoDataFrame(
        {"APN": ["A1", "A2"], "geometry": [poly, poly]}, crs="EPSG:4326"
    )

    async def cancelled():
        return True

    with pytest.raises(_asyncio.CancelledError):
        await ing.ingest_parcels(
            gdf, _uuid.uuid4(), _DB(), cancel_check=cancelled
        )
    assert upserted == [], "rows were upserted despite cancellation"
