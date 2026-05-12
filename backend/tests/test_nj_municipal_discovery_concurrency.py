"""Regression test: concurrent per-town discovery must not race on the
shared AsyncSession. The earlier bug had 3 concurrent town tasks all
calling _persist_candidates(db, ...) → db.commit() on the same session,
which interleaved and caused the second/third town's `persisted_count`
to return 0 even when rows landed in the DB.

The fix in `discover_municipal_zoning_for_county` adds an asyncio.Lock
around the persist+commit critical section. This test verifies the lock
serializes those sections by injecting a fake DB whose
`_persist_candidates`-side calls raise if invoked concurrently.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@dataclass
class _FakeJurisdiction:
    id: str = "fake-county-id"
    name: str = "Fake County, NJ"
    state: str = "NJ"
    county: str = "Fake"


@pytest.mark.asyncio
async def test_concurrent_town_persist_is_serialized(monkeypatch):
    """3 concurrent town tasks → all must report persisted_count > 0.

    Verifies asyncio.Lock serializes the persist+commit critical section
    so the second/third concurrent town's count isn't silently zeroed by
    a shared-session race.
    """
    from app.services import nj_municipal_discovery as svc

    in_flight = 0
    max_in_flight = 0
    invocation_count = 0

    async def fake_persist_candidates(db, jurisdiction, candidates, municipality_name):
        nonlocal in_flight, max_in_flight, invocation_count
        in_flight += 1
        invocation_count += 1
        max_in_flight = max(max_in_flight, in_flight)
        # Simulate DB work — give other tasks a chance to interleave if
        # the lock isn't doing its job.
        await asyncio.sleep(0.05)
        in_flight -= 1

    async def fake_hub_search(client, query, bbox_str):
        return [{"id": "fake-ds-1", "title": "Fake Zoning"}]

    fake_candidate = MagicMock()
    fake_candidate.url = "https://fake.example.com/FeatureServer/0"
    fake_candidate.title = "Fake Zoning"
    fake_candidate.confidence = 80
    fake_candidate.feature_count = 100
    fake_candidate.geometry_type = "esriGeometryPolygon"
    fake_candidate.source_type = "arcgis_featureserver"
    fake_candidate.field_matches = []
    fake_candidate.reasons = []

    async def fake_probe_layer(client, item, bbox, name_tokens, **kwargs):
        return fake_candidate

    fake_jurisdiction = _FakeJurisdiction()

    # AsyncSession mock; execute() is async + returns an object whose
    # .scalar_one_or_none() returns None. commit() is async no-op.
    fake_db = MagicMock()
    fake_db.get = AsyncMock(return_value=fake_jurisdiction)
    fake_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))
    fake_db.commit = AsyncMock(return_value=None)
    fake_db.add = MagicMock()

    monkeypatch.setattr(svc, "_persist_candidates", fake_persist_candidates)
    monkeypatch.setattr(svc, "_hub_search", fake_hub_search)
    monkeypatch.setattr(svc, "_probe_layer", fake_probe_layer)

    result = await svc.discover_municipal_zoning_for_county(
        county_jurisdiction_id="fake-county-id",
        db=fake_db,
        municipality_names=["TownA", "TownB", "TownC"],
    )

    # All three towns must report persisted_count > 0 (the bug returned 0
    # for towns 2-3 of any concurrent batch).
    for r in result["results"]:
        assert r["persisted_count"] > 0, (
            f"town {r['municipality_name']!r} returned persisted_count=0 "
            "— concurrent-commit race regressed"
        )
        assert r["error"] is None

    # Persist must have run exactly once per town (3 invocations total).
    assert invocation_count == 3

    # And critically: the lock must have serialized the critical section,
    # so max_in_flight == 1 across the 3 concurrent tasks.
    assert max_in_flight == 1, (
        f"persist critical section ran with {max_in_flight} concurrent tasks "
        "— lock isn't serializing as expected"
    )
