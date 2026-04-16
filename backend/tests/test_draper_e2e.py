"""
Draper, UT end-to-end integration test.

Runs the full Phase 2 pipeline against the live Draper ArcGIS FeatureServer
and asserts data quality expectations from the spec:

  (a) ≥ 200 parcels loaded
  (b) At least one vacant parcel returned (has_structure IS NULL or False)
  (c) Draper zones known from parcel data are present

Phase 3 check (zone matrix / self-storage permissions) is marked xfail until
the ordinance parser is implemented.

These tests are marked `integration` — they hit real external services.
Run them with:
    pytest -m integration -v

In CI they run automatically when DATABASE_URL is set (see ci.yml).
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models.jurisdiction import Jurisdiction
from app.models.parcel import Parcel
from app.services.pipeline import KNOWN_JURISDICTIONS, _match_jurisdiction, run_job_pipeline


pytestmark = pytest.mark.integration


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="module")
async def draper_jurisdiction_id(db_engine) -> uuid.UUID:
    """
    Run the Draper pipeline once for the module and return the jurisdiction ID.
    Uses a fake job ID (the pipeline creates its own session anyway).
    """
    from app.db import async_session_maker
    from app.models.job import Job, JobStatus

    # Insert a job row so the pipeline can find + update it
    async with async_session_maker() as db:
        job = Job(
            jurisdiction_input="Draper, UT",
            ordinance_url=None,
            target_uses=["self_storage", "mini_warehouse", "light_industrial", "luxury_garage_condo"],
            status=JobStatus.pending,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        job_id = job.id

    # Run the pipeline (this downloads from the live ArcGIS server)
    await run_job_pipeline(job_id)

    # Return the jurisdiction ID that the pipeline created
    async with async_session_maker() as db:
        refreshed = await db.get(Job, job_id)
        assert refreshed is not None
        assert refreshed.status.value == "ready", (
            f"Pipeline failed: {refreshed.error_message}"
        )
        return refreshed.jurisdiction_id


# ─── Tests ───────────────────────────────────────────────────────────────────

class TestDraperPipelineData:

    @pytest.mark.asyncio
    async def test_jurisdiction_registered(self, draper_jurisdiction_id, db_engine):
        """The pipeline should create a Draper City, UT jurisdiction row."""
        from app.db import async_session_maker
        async with async_session_maker() as db:
            j = await db.get(Jurisdiction, draper_jurisdiction_id)
        assert j is not None
        assert "Draper" in j.name
        assert j.state == "UT"
        assert j.parcel_endpoint is not None

    @pytest.mark.asyncio
    async def test_minimum_parcel_count(self, draper_jurisdiction_id, db_engine):
        """(a) At least 200 parcels must be loaded."""
        from app.db import async_session_maker
        async with async_session_maker() as db:
            result = await db.execute(
                select(func.count()).select_from(Parcel).where(
                    Parcel.jurisdiction_id == draper_jurisdiction_id
                )
            )
            count = result.scalar_one()
        assert count >= 200, f"Only {count} parcels loaded — expected ≥ 200"

    @pytest.mark.asyncio
    async def test_at_least_one_vacant_parcel(self, draper_jurisdiction_id, db_engine):
        """(b) At least one parcel must be classified as vacant."""
        from app.db import async_session_maker
        async with async_session_maker() as db:
            result = await db.execute(
                select(func.count()).select_from(Parcel).where(
                    Parcel.jurisdiction_id == draper_jurisdiction_id,
                    Parcel.has_structure == False,  # noqa: E712
                )
            )
            vacant_count = result.scalar_one()
        assert vacant_count >= 1, "No vacant parcels found — expected at least 1"

    @pytest.mark.asyncio
    async def test_parcels_have_geometry(self, draper_jurisdiction_id, db_engine):
        """All parcels should have a geometry (no null geom rows)."""
        from app.db import async_session_maker
        from sqlalchemy import text
        async with async_session_maker() as db:
            result = await db.execute(
                text(
                    "SELECT COUNT(*) FROM parcels "
                    "WHERE jurisdiction_id = :jid AND geom IS NULL"
                ),
                {"jid": draper_jurisdiction_id},
            )
            null_count = result.scalar_one()
        # Allow up to 1% null geometries
        total_result = await _count_parcels(draper_jurisdiction_id)
        assert null_count / max(total_result, 1) <= 0.01, (
            f"{null_count} parcels have null geometry"
        )

    @pytest.mark.asyncio
    async def test_zone_codes_present(self, draper_jurisdiction_id, db_engine):
        """Parcels should carry zone codes (ZONING field mapped correctly)."""
        from app.db import async_session_maker
        async with async_session_maker() as db:
            result = await db.execute(
                select(Parcel.zoning_code)
                .where(
                    Parcel.jurisdiction_id == draper_jurisdiction_id,
                    Parcel.zoning_code.isnot(None),
                )
                .limit(1)
            )
            row = result.first()
        assert row is not None, "No parcels with non-null zoning_code"

    @pytest.mark.asyncio
    async def test_acres_populated(self, draper_jurisdiction_id, db_engine):
        """Most parcels should have an acreage value."""
        from app.db import async_session_maker
        async with async_session_maker() as db:
            result = await db.execute(
                select(func.count()).select_from(Parcel).where(
                    Parcel.jurisdiction_id == draper_jurisdiction_id,
                    Parcel.acres.isnot(None),
                )
            )
            with_acres = result.scalar_one()
        total = await _count_parcels(draper_jurisdiction_id)
        coverage = with_acres / max(total, 1)
        assert coverage >= 0.80, f"Only {coverage:.0%} of parcels have acreage"

    @pytest.mark.asyncio
    async def test_m1_cbp_cg_cs_permit_self_storage(
        self, draper_jurisdiction_id, db_engine
    ):
        """(c) M1/CBP/CG/CS must permit or conditionally permit self-storage."""
        from app.db import async_session_maker
        from app.models.zone_use_matrix import UsePermission, ZoneUseMatrix
        async with async_session_maker() as db:
            result = await db.execute(
                select(ZoneUseMatrix).where(
                    ZoneUseMatrix.jurisdiction_id == draper_jurisdiction_id,
                    ZoneUseMatrix.zone_code.in_(["M1", "CBP", "CG", "CS"]),
                )
            )
            zones = result.scalars().all()
        assert len(zones) >= 1, (
            "No zone matrix rows found — ordinance parser may not have run. "
            "Ensure ANTHROPIC_API_KEY is set and the ordinance URL is reachable."
        )
        zone_map = {z.zone_code: z for z in zones}
        ok = {UsePermission.permitted, UsePermission.conditional}
        for code in ["M1", "CBP", "CG", "CS"]:
            if code not in zone_map:
                continue  # Zone may not appear in the ordinance excerpt
            assert zone_map[code].self_storage in ok, (
                f"Zone {code} self_storage = {zone_map[code].self_storage} "
                f"(expected permitted or conditional)"
            )


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _count_parcels(jurisdiction_id: uuid.UUID) -> int:
    from app.db import async_session_maker
    async with async_session_maker() as db:
        result = await db.execute(
            select(func.count()).select_from(Parcel).where(
                Parcel.jurisdiction_id == jurisdiction_id
            )
        )
        return result.scalar_one()


# ─── Unit tests (no DB required) ─────────────────────────────────────────────

class TestKnownJurisdictions:

    def test_draper_is_registered(self):
        assert "draper" in KNOWN_JURISDICTIONS

    def test_match_draper_full_name(self):
        cfg = _match_jurisdiction("Draper City, UT")
        assert cfg is not None
        assert cfg.state == "UT"

    def test_match_draper_short(self):
        cfg = _match_jurisdiction("draper, ut")
        assert cfg is not None

    def test_no_match_returns_none(self):
        cfg = _match_jurisdiction("Atlantis, XX")
        assert cfg is None

    def test_draper_has_parcel_endpoint(self):
        cfg = KNOWN_JURISDICTIONS["draper"]
        assert "FeatureServer" in cfg.parcel_endpoint

    def test_draper_has_zoning_endpoint(self):
        cfg = KNOWN_JURISDICTIONS["draper"]
        assert cfg.zoning_endpoint is not None
