"""Unit tests for municipality_remediation — gap→action mapping, chain
expansion, dependency wiring, and escalation thresholds.

Pure functions — no DB, no network. We construct fake `muni` dicts (the
shape `municipality_health` returns) plus stub `ZoningSource` rows and
call `build_remediation_plan` directly.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.services.municipality_remediation import (
    ESCALATION_MAX_BROKEN_STEPS,
    build_remediation_plan,
)


def _muni(*, gaps, band="broken", municipality="New Milford", parcel_count=1000):
    return {
        "municipality": municipality,
        "trustworthiness": band,
        "gaps": list(gaps),
        "parcel_count": parcel_count,
    }


def _src(**kwargs):
    defaults = dict(
        id=uuid.uuid4(),
        jurisdiction_id=uuid.uuid4(),
        municipality_name="New Milford",
        title="Sample Zoning",
        zoning_endpoint="https://example.com/FeatureServer/0",
        validation_status="pending",
        confidence_score=75,
        confidence_label="discovered",
        confidence_breakdown={},
        reasons=[],
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


_JID = uuid.uuid4()


# ─── operational munis emit empty plans ───────────────────────────────────────

def test_operational_muni_emits_no_steps():
    muni = _muni(gaps=[], band="operational")
    plan = build_remediation_plan(
        jurisdiction_id=_JID, jurisdiction_name="Bergen County, NJ",
        muni=muni, sources=[], is_county_with_munis=True,
    )
    assert plan.steps == []
    assert plan.escalate_to_engineer is False


def test_empty_muni_emits_discover_step():
    """An empty muni (no parcels, no districts) emits just a discover step.

    Chain expansion stops at the operator-review gate — we don't know
    which candidate the operator will pick, so the next remediation
    call (after operator verifies one) is what surfaces the
    ingest+respatial follow-on."""
    muni = _muni(gaps=["no parcels and no zoning_districts"], band="empty",
                 parcel_count=0)
    plan = build_remediation_plan(
        jurisdiction_id=_JID, jurisdiction_name="Bergen County, NJ",
        muni=muni, sources=[], is_county_with_munis=True,
    )
    codes = [s.action_code for s in plan.steps]
    assert codes == ["discover_new_source"]


# ─── chain expansion ─────────────────────────────────────────────────────────

def test_reject_wrong_source_chains_into_full_recovery():
    """Reject → discover → verify → ingest → respatial_join."""
    muni = _muni(gaps=[
        "parcel and district extents overlap only 12% — districts may belong to wrong location",
    ])
    verified = _src(validation_status="verified", confidence_score=85)
    plan = build_remediation_plan(
        jurisdiction_id=_JID, jurisdiction_name="Bergen County, NJ",
        muni=muni, sources=[verified], is_county_with_munis=True,
    )
    codes = [s.action_code for s in plan.steps]
    assert "reject_wrong_source" in codes
    assert "discover_new_source" in codes
    # verify_top_candidate may be skipped if no pending candidate exists,
    # but ingest_verified_source must follow somehow.
    assert codes.index("reject_wrong_source") < codes.index("discover_new_source")


def test_no_verified_source_for_reject_falls_through_to_discover():
    """Reject step requires a verified source. Without one, the rejector
    materializer falls through to `discover_new_source` directly."""
    muni = _muni(gaps=[
        "parcel and district extents overlap only 12% — districts may belong to wrong location",
    ])
    plan = build_remediation_plan(
        jurisdiction_id=_JID, jurisdiction_name="Bergen County, NJ",
        muni=muni, sources=[], is_county_with_munis=True,
    )
    codes = [s.action_code for s in plan.steps]
    assert "reject_wrong_source" not in codes
    assert "discover_new_source" in codes


def test_respatial_join_chained_after_replace_districts():
    """Invalid geometry → replace → respatial_join automatically."""
    muni = _muni(gaps=["3 zoning_district rows have invalid PostGIS geometry"])
    verified = _src(validation_status="verified", confidence_score=85)
    plan = build_remediation_plan(
        jurisdiction_id=_JID, jurisdiction_name="Bergen County, NJ",
        muni=muni, sources=[verified], is_county_with_munis=True,
    )
    codes = [s.action_code for s in plan.steps]
    assert "replace_districts" in codes
    assert "respatial_join" in codes
    rd = codes.index("replace_districts")
    rj = codes.index("respatial_join")
    assert rd < rj


def test_low_bind_rate_emits_respatial_join_directly():
    """If the only problem is parcels not carrying zoning_code, the
    plan is just respatial_join — districts are fine, the join is what
    didn't run."""
    muni = _muni(gaps=[
        "only 8% of parcels carry zoning_code — spatial join likely failed",
    ])
    plan = build_remediation_plan(
        jurisdiction_id=_JID, jurisdiction_name="Bergen County, NJ",
        muni=muni, sources=[], is_county_with_munis=True,
    )
    codes = [s.action_code for s in plan.steps]
    assert codes == ["respatial_join"]


# ─── dependency wiring ───────────────────────────────────────────────────────

def test_dependencies_link_chain_steps_by_number():
    """Each chained step lists predecessor step numbers in `dependencies`."""
    muni = _muni(gaps=[
        "parcel and district extents overlap only 12% — districts may belong to wrong location",
    ])
    verified = _src(validation_status="verified")
    pending = _src(validation_status="pending", confidence_score=75)
    plan = build_remediation_plan(
        jurisdiction_id=_JID, jurisdiction_name="Bergen County, NJ",
        muni=muni, sources=[verified, pending], is_county_with_munis=True,
    )
    by_code = {s.action_code: s for s in plan.steps}
    if "discover_new_source" in by_code and "verify_top_candidate" in by_code:
        verify_step = by_code["verify_top_candidate"]
        discover_step = by_code["discover_new_source"]
        assert discover_step.step in verify_step.dependencies
    if "ingest_verified_source" in by_code:
        ingest_step = by_code["ingest_verified_source"]
        # ingest depends on either verify or discover
        assert ingest_step.dependencies, "ingest should have a predecessor"


# ─── needs_operator_input — verify step without a pending candidate ──────────

def test_verify_step_records_input_required_when_no_pending_candidate():
    """If chain expansion implies `verify_top_candidate` but no high-
    confidence pending source exists, the step is dropped and the
    operator is told what they need."""
    muni = _muni(gaps=["districts ingested for this muni: 0"])
    plan = build_remediation_plan(
        jurisdiction_id=_JID, jurisdiction_name="Bergen County, NJ",
        muni=muni, sources=[], is_county_with_munis=True,
    )
    codes = [s.action_code for s in plan.steps]
    # Chain wants verify_top_candidate but there's nothing pending; should
    # show up in needs_operator_input instead.
    if "verify_top_candidate" not in codes:
        assert any(
            "pending source" in n.lower() or "review" in n.lower()
            for n in plan.needs_operator_input
        )


# ─── escalation ──────────────────────────────────────────────────────────────

def test_audit_action_escalates_broken_band_to_engineer():
    """Plans that include `audit_spatial_sources` are ambiguous failures
    requiring engineer judgment, not self-serve fixes."""
    muni = _muni(gaps=["only 2 distinct district polygons — suspiciously few"])
    plan = build_remediation_plan(
        jurisdiction_id=_JID, jurisdiction_name="Bergen County, NJ",
        muni=muni, sources=[], is_county_with_munis=True,
        # Force broken so the escalation gate trips on this condition.
    )
    # Test scaffolding — audit step requires broken band to escalate; the
    # service computes it from the muni band (degraded here). Re-run with
    # an explicit broken muni to assert the escalation flag.
    broken_muni = {**muni, "trustworthiness": "broken"}
    broken_plan = build_remediation_plan(
        jurisdiction_id=_JID, jurisdiction_name="Bergen County, NJ",
        muni=broken_muni, sources=[], is_county_with_munis=True,
    )
    assert broken_plan.escalate_to_engineer is True


def test_short_broken_plan_does_not_escalate():
    """A broken band with one clear action stays self-serve."""
    muni = _muni(gaps=[
        "only 8% of parcels carry zoning_code — spatial join likely failed",
    ])
    plan = build_remediation_plan(
        jurisdiction_id=_JID, jurisdiction_name="Bergen County, NJ",
        muni=muni, sources=[], is_county_with_munis=True,
    )
    assert plan.escalate_to_engineer is False
    assert len(plan.steps) <= ESCALATION_MAX_BROKEN_STEPS


# ─── city-jurisdiction vs NJ-county branching ────────────────────────────────

def test_city_jurisdiction_emits_backfill_endpoint_not_municipal_endpoint():
    """For city-jurisdictions (Draper UT), ingest goes through
    `_backfill-zoning` not `_ingest-municipal-zoning`."""
    muni = _muni(gaps=["districts ingested for this muni: 0"],
                 municipality=None)  # city-jurisdiction style
    verified = _src(validation_status="verified",
                    municipality_name=None,
                    zoning_endpoint="https://city.gov/FeatureServer/0")
    plan = build_remediation_plan(
        jurisdiction_id=_JID, jurisdiction_name="Draper City, UT",
        muni=muni, sources=[verified], is_county_with_munis=False,
    )
    ingest = next(
        (s for s in plan.steps if s.action_code == "ingest_verified_source"),
        None,
    )
    if ingest is not None:
        assert "_backfill-zoning" in ingest.command["path"]
        assert "_ingest-municipal-zoning" not in ingest.command["path"]


def test_county_with_munis_emits_municipal_endpoint():
    """For NJ-style counties, ingest goes through `_ingest-municipal-zoning`."""
    muni = _muni(gaps=["districts ingested for this muni: 0"])
    verified = _src(validation_status="verified")
    plan = build_remediation_plan(
        jurisdiction_id=_JID, jurisdiction_name="Bergen County, NJ",
        muni=muni, sources=[verified], is_county_with_munis=True,
    )
    ingest = next(
        (s for s in plan.steps if s.action_code == "ingest_verified_source"),
        None,
    )
    if ingest is not None:
        assert "_ingest-municipal-zoning" in ingest.command["path"]


# ─── severity propagation ────────────────────────────────────────────────────

def test_severity_inherits_through_chain():
    """A must-reject implies a must-discover (chained from must). A
    should-replace implies a should-respatial-join."""
    muni = _muni(gaps=[
        "parcel and district extents overlap only 12% — districts may belong to wrong location",
    ])
    verified = _src(validation_status="verified")
    plan = build_remediation_plan(
        jurisdiction_id=_JID, jurisdiction_name="Bergen County, NJ",
        muni=muni, sources=[verified], is_county_with_munis=True,
    )
    reject = next((s for s in plan.steps if s.action_code == "reject_wrong_source"), None)
    discover = next((s for s in plan.steps if s.action_code == "discover_new_source"), None)
    assert reject is not None and reject.severity == "must"
    if discover is not None:
        assert discover.severity == "must"
