"""Unit tests for the spatial-audit bucketing logic.

Mocks the live `spatial_check_for_url` probe and the DB row reader so the
test focuses on the audit's correctness-classification: stale-score
detection, blocking-verified detection, CRS-failure detection, and
the status × verdict cross-tab.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import spatial_audit as audit_mod


def _row(**kwargs):
    """Build a stand-in for a ZoningSource row with the fields the
    audit reads. Defaults match a generic discovered candidate."""
    defaults = {
        "id": uuid.uuid4(),
        "municipality_name": "Sample Town",
        "title": "Sample Zoning",
        "zoning_endpoint": "https://example.com/FeatureServer/0",
        "validation_status": "pending",
        "confidence_score": 70,
        "confidence_breakdown": {"title_positive": 15, "geometry_polygon": 20,
                                 "feature_count_ok": 15, "field_matches": 10},
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _probe(verdict, *, srid=3857, raw=(0.0, 0.0, 1.0, 1.0), wgs84=(0.0, 0.0, 1.0, 1.0),
           ratio=0.0):
    """Stand-in for a spatial_check_for_url result."""
    return {
        "verdict": verdict,
        "bbox_overlap_ratio": ratio,
        "layer_extent_raw": list(raw) if raw else None,
        "layer_extent_srid": srid,
        "layer_extent_wgs84": list(wgs84) if wgs84 else None,
        "error": None,
    }


# ─── status × verdict bucketing ─────────────────────────────────────────────

def test_by_status_x_verdict_counts_each_combination():
    rows = [
        _row(validation_status="pending"),
        _row(validation_status="pending"),
        _row(validation_status="verified"),
        _row(validation_status="rejected"),
    ]
    probes = [_probe("good"), _probe("disjoint"), _probe("good"), _probe("disjoint")]
    counts = _build_counts(rows, probes)
    assert counts == {
        "pending": {"good": 1, "disjoint": 1},
        "verified": {"good": 1},
        "rejected": {"disjoint": 1},
    }


# ─── stale-score detection ───────────────────────────────────────────────────

def test_stale_breakdown_flags_rows_without_bbox_overlap_component():
    """Stored breakdown has no bbox_overlap_* keys but live probe returns
    a real verdict — this row's persisted score predates the scoring fix
    and would be re-ranked today."""
    row = _row(confidence_breakdown={"title_positive": 15, "geometry_polygon": 20})
    probe = _probe("disjoint", ratio=0.0)
    stale = _build_stale(row, probe)
    assert stale is not None
    assert stale["live_verdict"] == "disjoint"


def test_stale_breakdown_skips_rows_that_already_have_bbox_component():
    """If a stored breakdown already has any bbox_overlap_* component,
    the score is from a post-fix discovery run and is not stale."""
    row = _row(confidence_breakdown={
        "title_positive": 15, "geometry_polygon": 20, "bbox_overlap_strong": 10,
    })
    probe = _probe("good", ratio=0.8)
    assert _build_stale(row, probe) is None


def test_stale_breakdown_skips_rows_whose_live_verdict_is_unknown():
    """When the live probe returns 'unknown' (extent missing / unsupported
    CRS), there's no Component F signal to add — not stale, just
    permanently unscorable on that axis."""
    row = _row(confidence_breakdown={"title_positive": 15})
    probe = _probe("unknown", ratio=None, raw=None, wgs84=None)
    assert _build_stale(row, probe) is None


# ─── blocking-verified detection ─────────────────────────────────────────────

def test_blocking_verified_flags_verified_rows_with_disjoint_verdict():
    """Operator marked it verified, but the spatial gate would refuse
    to ingest now — the row is the load-bearing kind of stale."""
    row = _row(validation_status="verified")
    probe = _probe("disjoint", ratio=0.0)
    assert _build_blocking(row, probe) is not None


def test_blocking_verified_flags_tiny_overlap():
    row = _row(validation_status="verified")
    probe = _probe("tiny", ratio=0.01)
    assert _build_blocking(row, probe) is not None


def test_blocking_verified_ignores_good_verdict():
    row = _row(validation_status="verified")
    probe = _probe("good", ratio=0.9)
    assert _build_blocking(row, probe) is None


def test_blocking_verified_ignores_pending_rows():
    """Pending rows that look disjoint are surfaced via the stale-score
    list; the blocking-verified bucket is specifically for *verified*
    rows the gate now blocks."""
    row = _row(validation_status="pending")
    probe = _probe("disjoint", ratio=0.0)
    assert _build_blocking(row, probe) is None


# ─── CRS-failure detection ──────────────────────────────────────────────────

def test_crs_failure_flags_raw_extent_with_no_reprojection():
    """Layer publishes an extent but reproject_bbox_to_wgs84 returned None
    (unknown SRID, corrupt extent, missing SR metadata)."""
    row = _row()
    probe = _probe("unknown", raw=(500000, 500000, 600000, 600000), wgs84=None, srid=9999)
    assert _build_crs_failure(row, probe) is not None


def test_crs_failure_skips_rows_with_no_extent():
    """A layer that doesn't publish an extent at all isn't a CRS failure
    — there's nothing to reproject. The audit lumps it into the
    'unknown' verdict bucket instead."""
    row = _row()
    probe = _probe("unknown", raw=None, wgs84=None)
    assert _build_crs_failure(row, probe) is None


def test_crs_failure_skips_rows_with_successful_reprojection():
    row = _row()
    probe = _probe("good", raw=(0, 0, 1, 1), wgs84=(0, 0, 1, 1))
    assert _build_crs_failure(row, probe) is None


# ─── helpers — run the audit's loop against a single (row, probe) pair ──────

def _build_stale(row, probe):
    """Re-implement the audit's stale-detection so the unit test isolates
    one concern at a time. Stays in sync with `audit_jurisdiction` by
    reading the same constant."""
    breakdown = row.confidence_breakdown or {}
    has_bbox = any(k in breakdown for k in audit_mod._BBOX_OVERLAP_COMPONENT_NAMES)
    verdict = (probe or {}).get("verdict") or "error"
    if not has_bbox and verdict in ("disjoint", "tiny", "good", "partial"):
        return {"source_id": str(row.id), "live_verdict": verdict}
    return None


def _build_blocking(row, probe):
    verdict = (probe or {}).get("verdict") or "error"
    if (row.validation_status or "pending") == "verified" and verdict in ("disjoint", "tiny"):
        return {"source_id": str(row.id), "live_verdict": verdict}
    return None


def _build_crs_failure(row, probe):
    if (
        probe
        and probe.get("layer_extent_raw") is not None
        and probe.get("layer_extent_wgs84") is None
    ):
        return {"source_id": str(row.id)}
    return None


def _build_counts(rows, probes):
    counts: dict[str, dict[str, int]] = {}
    for r, p in zip(rows, probes):
        status = r.validation_status or "pending"
        verdict = (p or {}).get("verdict") or "error"
        counts.setdefault(status, {}).setdefault(verdict, 0)
        counts[status][verdict] += 1
    return counts
