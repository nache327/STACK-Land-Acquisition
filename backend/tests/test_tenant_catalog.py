"""Unit tests for tenant_catalog — pure-Python parsing + matching.

No DB and no network — tests use a temp catalog file via monkeypatching the
module-level _CATALOG_PATH constant.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services import tenant_catalog as tc


@pytest.fixture
def tmp_catalog(tmp_path, monkeypatch):
    """Point tenant_catalog at a temp JSON file with a controlled seed."""
    p = tmp_path / "zoning_source_tenants.json"
    p.write_text(json.dumps({
        "_meta": {"version": 1},
        "tenants": {
            "services6.arcgis.com/UcuMPLF9IlsigGHI": {
                "vendor": "Test vendor",
                "verified_munis": [
                    {"muni": "Paramus", "state": "NJ", "service_name": "Paramus_Zoning"}
                ],
                "candidate_munis": [
                    {"muni": "Westwood", "state": "NJ", "service_name": "Westwood_Zoning_2019"}
                ],
            },
            "services1.arcgis.com/abc123": {
                "vendor": "Empty entry",
                "verified_munis": [],
                "candidate_munis": [],
            },
        },
        "denylist": {
            "prefixes": ["services3.arcgis.com/m3XdyJh55Jrxxk0l"],
        },
    }))
    monkeypatch.setattr(tc, "_CATALOG_PATH", p)
    return p


def test_tenant_prefix_arcgis_online():
    assert tc.tenant_prefix(
        "https://services6.arcgis.com/UcuMPLF9IlsigGHI/arcgis/rest/services/Paramus_Zoning/FeatureServer/0"
    ) == "services6.arcgis.com/UcuMPLF9IlsigGHI"


def test_tenant_prefix_case_insensitive_arcgis_segment():
    assert tc.tenant_prefix(
        "https://services1.arcgis.com/ze0XBzU1FXj94DJq/ArcGIS/rest/services/X/FeatureServer"
    ) == "services1.arcgis.com/ze0XBzU1FXj94DJq"


def test_tenant_prefix_returns_none_for_non_arcgis():
    assert tc.tenant_prefix("https://example.com/whatever") is None
    assert tc.tenant_prefix("https://maps.nj.gov/arcgis/rest/services/Zoning") is None  # not services{n}.arcgis.com
    assert tc.tenant_prefix(None) is None
    assert tc.tenant_prefix("") is None


def test_is_known_tenant_only_when_verified(tmp_catalog):
    assert tc.is_known_tenant(
        "https://services6.arcgis.com/UcuMPLF9IlsigGHI/arcgis/rest/services/Whatever/FeatureServer"
    ) is True
    # Tenant exists in catalog but has no verified_munis — not known
    assert tc.is_known_tenant(
        "https://services1.arcgis.com/abc123/arcgis/rest/services/Foo/FeatureServer"
    ) is False
    assert tc.is_known_tenant("https://services9.arcgis.com/unknown/arcgis/rest/services/X") is False


def test_is_denylisted_tenant(tmp_catalog):
    assert tc.is_denylisted_tenant(
        "https://services3.arcgis.com/m3XdyJh55Jrxxk0l/arcgis/rest/services/Zoning/FeatureServer/0"
    ) is True
    assert tc.is_denylisted_tenant(
        "https://services6.arcgis.com/UcuMPLF9IlsigGHI/arcgis/rest/services/Paramus_Zoning/FeatureServer/0"
    ) is False


def test_known_tenants_returns_only_verified(tmp_catalog):
    out = tc.known_tenants()
    assert "services6.arcgis.com/UcuMPLF9IlsigGHI" in out
    assert "services1.arcgis.com/abc123" not in out


@pytest.mark.asyncio
async def test_add_verified_muni_appends_and_promotes(tmp_catalog):
    # Verify Westwood (currently a candidate) — should remove from candidate list + append to verified.
    result = await tc.add_verified_muni(
        "https://services6.arcgis.com/UcuMPLF9IlsigGHI/arcgis/rest/services/Westwood_Zoning_2019/FeatureServer/0",
        "Westwood", "NJ", "Westwood_Zoning_2019",
    )
    assert result is True
    cat = json.loads(tmp_catalog.read_text())
    entry = cat["tenants"]["services6.arcgis.com/UcuMPLF9IlsigGHI"]
    verified = {(v["muni"], v["state"], v["service_name"]) for v in entry["verified_munis"]}
    assert ("Westwood", "NJ", "Westwood_Zoning_2019") in verified
    assert ("Paramus", "NJ", "Paramus_Zoning") in verified
    candidates = entry["candidate_munis"]
    assert all(c["muni"] != "Westwood" for c in candidates)


@pytest.mark.asyncio
async def test_add_verified_muni_is_idempotent(tmp_catalog):
    args = (
        "https://services6.arcgis.com/UcuMPLF9IlsigGHI/arcgis/rest/services/Paramus_Zoning/FeatureServer/0",
        "Paramus", "NJ", "Paramus_Zoning",
    )
    first = await tc.add_verified_muni(*args)
    second = await tc.add_verified_muni(*args)
    assert first is False  # Already in seed
    assert second is False


@pytest.mark.asyncio
async def test_add_verified_muni_creates_new_tenant(tmp_catalog):
    result = await tc.add_verified_muni(
        "https://services1.arcgis.com/NEWTENANT/arcgis/rest/services/Hackensack_Zoning/FeatureServer/0",
        "Hackensack", "NJ", "Hackensack_Zoning",
    )
    assert result is True
    cat = json.loads(tmp_catalog.read_text())
    assert "services1.arcgis.com/NEWTENANT" in cat["tenants"]


@pytest.mark.asyncio
async def test_add_verified_muni_swallows_bad_input(tmp_catalog):
    # Non-arcgis URL — silently False, doesn't raise
    assert await tc.add_verified_muni("https://example.com", "X", "NJ", "Y") is False
    # None muni — silently False
    assert await tc.add_verified_muni(
        "https://services6.arcgis.com/UcuMPLF9IlsigGHI/arcgis/rest/services/Z/FeatureServer/0",
        None, "NJ", "Z",
    ) is False


def test_is_zoning_service_name_underscore_aware():
    # Iteration-1 bug: regex \b in Python treats _ as a word char, so this failed.
    assert tc.is_zoning_service_name("Paramus_Zoning") is True
    assert tc.is_zoning_service_name("Westwood_Zoning_2019") is True
    assert tc.is_zoning_service_name("MyTown_LandUse") is True
    assert tc.is_zoning_service_name("Closter_MS4_Infrastructure_Map") is False
    assert tc.is_zoning_service_name("Bergen_BLD") is False


def test_matches_municipality_strict():
    # Full muni concat in service name
    assert tc.matches_municipality("Westwood_Zoning_2019", "Westwood") is True
    # Multi-word muni — all tokens required
    assert tc.matches_municipality("Franklin_Lakes_Zoning", "Franklin Lakes") is True
    assert tc.matches_municipality("Franklin_County_Zoning_Map_WFL1", "Franklin Lakes") is False
    assert tc.matches_municipality("Lakes_Zoning_Plan", "Franklin Lakes") is False
    # Single short token should not match
    assert tc.matches_municipality("Old_Zoning_Plan", "Old Tappan") is False  # "Old" is 3 chars
    # Single rare token (>=7 chars) matches
    assert tc.matches_municipality("Hackensack_Zoning", "Hackensack") is True
    # Cross-state collision suppressed (relies on the directory not having a 7+-char-name-only collision)
    assert tc.matches_municipality("Garfield_County_Zoning_Utah", "Garfield") is True  # match — but caller's other heuristics (wrong_state) should reject


def test_matches_municipality_handles_separators():
    # Hub data has both underscore- and hyphen- and concat-separated names
    assert tc.matches_municipality("Englewood-Zoning-Districts", "Englewood") is True
    assert tc.matches_municipality("WestwoodZoning2019", "Westwood") is True


@pytest.mark.asyncio
async def test_tenant_directory_sweep_filters_to_zoning_and_bergen(tmp_catalog, monkeypatch):
    """Stub enumerate_tenant_services to return a controlled service list and
    verify the sweep only yields zoning+bergen-matched candidates."""
    bergen_munis = ["Paramus", "Westwood", "Franklin Lakes", "Hackensack", "Teaneck", "Closter"]
    fake_services = [
        {"name": "Paramus_Zoning_Rev2023", "type": "FeatureServer", "url": "u1"},
        {"name": "Westwood_Zoning_2019", "type": "FeatureServer", "url": "u2"},
        {"name": "Closter_MS4_Infrastructure_Map", "type": "FeatureServer", "url": "u3"},  # not zoning
        {"name": "Franklin_County_Zoning_Utah", "type": "FeatureServer", "url": "u4"},     # zoning but not Bergen Franklin Lakes
        {"name": "Hawthorne_Zoning", "type": "FeatureServer", "url": "u5"},                # not in muni list
    ]
    async def fake_enum(tenant, **kw):
        return fake_services
    monkeypatch.setattr(tc, "enumerate_tenant_services", fake_enum)

    out = await tc.tenant_directory_sweep(bergen_munis)
    munis = {(c["muni"], c["service_name"]) for c in out}
    assert ("Paramus", "Paramus_Zoning_Rev2023") in munis
    assert ("Westwood", "Westwood_Zoning_2019") in munis
    # Filtered out: Closter_MS4 (not zoning), Franklin_County_Zoning_Utah (no
    # token match for Franklin Lakes), Hawthorne_Zoning (not in muni list).
    assert len(out) == 2
