"""Bulk re-score for stale zoning_sources rows.

The Bergen audit (iteration 1) found 664/710 rows with persisted scores
that predate the 2026-05-12 pyproj + bbox-overlap fixes. The stored
`confidence_breakdown` for those rows lacks any `bbox_overlap_*`
component — re-running discovery's scoring against current logic
re-ranks them (typically dropping the wrong-jurisdiction candidates by
-60 from the `bbox_overlap_disjoint` penalty).

This module re-scores rows in place WITHOUT re-running Hub search:

  - For each row, fetch the layer's live extent via `spatial_check_for_url`
    (the same probe used by the audit) and recompute Component F.
  - Replay `_score_candidate` against the row's persisted static fields
    (title, feature_count, geometry_type, field_matches) + the live
    bbox-overlap ratio + the live denylist.
  - In dry-run mode (the default): return the full before/after diff, no
    DB writes.
  - In live mode: write the new (score, label, breakdown, reasons) to
    rows whose validation_status is `pending` only. Verified and rejected
    rows are SCANNED (and reported in the diff for visibility) but never
    mutated — operator decisions are durable.

Safety guarantees:
  - `dry_run` defaults to True. Live mode requires explicit `dry_run=false`.
  - `max_rows` is enforced; default 200.
  - Verified + rejected rows are never written to.
  - validation_status, rejected_reason, notes, last_verified_at, created_at
    are never mutated by this code path (only confidence_* + reasons +
    updated_at).
  - The response includes the complete pre-change snapshot for every
    row touched, so the operator can save it client-side and submit it
    to `rollback_rescores()` if something goes wrong.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.jurisdiction import Jurisdiction
from app.models.zoning_source import ZoningSource
from app.services.zoning_discovery import (
    SCORING_VERSION,
    SCORING_VERSION_MARKERS,
    _ZONING_KEYWORDS_NEGATIVE,
    _ZONING_KEYWORDS_POSITIVE,
    _fetch_rejected_endpoints,
    _name_match_signals,
    _name_tokens,
    _score_candidate,
    spatial_check_for_url,
)

logger = logging.getLogger(__name__)

# Component F component names — used to detect stale rows.
_BBOX_OVERLAP_COMPONENT_NAMES = (
    "bbox_overlap_strong",
    "bbox_overlap_tiny",
    "bbox_overlap_disjoint",
)

# Default age cap for the "row hasn't been re-scored recently" eligibility
# reason. Operator can override via the endpoint; 90 days is the
# pragmatic floor — most muni ArcGIS publishers refresh quarterly.
_DEFAULT_MAX_AGE_DAYS = 90

# Threshold operator uses for queue triage (mirrors nj_municipal_discovery).
_QUEUE_THRESHOLD = 70

# Hard cap on rows touched in one call. Even with --max-rows higher, we
# stop here to keep latency + operator review load bounded.
_HARD_ROW_CAP = 1000

_DEFAULT_CONCURRENCY = 8

# Statuses we are *allowed* to mutate in live mode. Verified + rejected
# rows are operator decisions; we never overwrite them.
_MUTABLE_STATUSES = frozenset({"pending", "needs_review"})


@dataclass
class RescoreOptions:
    """Inputs to `rescore_stale_sources`."""
    dry_run: bool = True
    source_ids: list[uuid.UUID] | None = None
    max_rows: int = 200
    only_status: tuple[str, ...] | None = ("pending",)
    stale_only: bool = True
    concurrency: int = _DEFAULT_CONCURRENCY


async def rescore_stale_sources(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession,
    opts: RescoreOptions,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Re-score stale zoning_sources rows for one jurisdiction.

    Returns a structured diff. When opts.dry_run is False, also writes
    the new (confidence_score, confidence_label, confidence_breakdown,
    reasons) to non-verified, non-rejected rows — every other column
    on zoning_sources is untouched.
    """
    juris = await db.get(Jurisdiction, jurisdiction_id)
    if juris is None:
        return {"error": "jurisdiction not found", "jurisdiction_id": str(jurisdiction_id)}

    rows = await _load_target_rows(jurisdiction_id, opts, db)
    rows = rows[: min(opts.max_rows, _HARD_ROW_CAP)]

    if not rows:
        return _empty_response(juris, opts, scanned=0)

    name_tokens = _name_tokens(juris.name, juris.county)
    denylist = await _fetch_rejected_endpoints(db)

    probes = await _probe_rows(rows, juris.bbox, opts.concurrency, http_client)

    changes: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    applied_count = 0
    skipped_immutable_count = 0

    now = datetime.now(timezone.utc)
    for row, probe in zip(rows, probes):
        try:
            recomputed = _recompute_row(
                row=row,
                probe=probe,
                jurisdiction=juris,
                name_tokens=name_tokens,
                denylist=denylist,
            )
        except Exception as exc:
            logger.warning("rescore failed for %s: %r", row.id, exc)
            errors.append({"source_id": str(row.id), "error": repr(exc)[:200]})
            continue

        before = _snapshot(row)
        after = recomputed["after"]
        delta = (after["confidence_score"] or 0) - (before["confidence_score"] or 0)

        # An applied change has effect only when at least one of
        # confidence_score / confidence_breakdown / reasons / confidence_label
        # would change. Rows where everything stays identical aren't
        # reported as "changes" — they're tallied in summary.no_change.
        is_no_op = (
            after["confidence_score"] == before["confidence_score"]
            and after["confidence_breakdown"] == before["confidence_breakdown"]
            and after["confidence_label"] == before["confidence_label"]
            and after["reasons"] == before["reasons"]
        )

        change_record = {
            "source_id": str(row.id),
            "municipality_name": row.municipality_name,
            "title": row.title,
            "zoning_endpoint": row.zoning_endpoint,
            "validation_status": row.validation_status,
            "before": before,
            "after": after,
            "delta": delta,
            "crosses_threshold_70": _crosses_threshold(
                before["confidence_score"], after["confidence_score"], _QUEUE_THRESHOLD,
            ),
            "live_verdict": (probe or {}).get("verdict"),
            "live_overlap_ratio": (probe or {}).get("bbox_overlap_ratio"),
        }

        will_write = (
            not opts.dry_run
            and not is_no_op
            and (row.validation_status in _MUTABLE_STATUSES)
        )

        if will_write:
            row.confidence_score = after["confidence_score"]
            row.confidence_label = after["confidence_label"]
            row.confidence_breakdown = after["confidence_breakdown"]
            row.reasons = after["reasons"]
            row.updated_at = now
            applied_count += 1
            change_record["applied"] = True
        else:
            change_record["applied"] = False
            if not opts.dry_run and not is_no_op and (
                row.validation_status not in _MUTABLE_STATUSES
            ):
                # Row would change but is verified/rejected — preserve.
                change_record["skipped_reason"] = (
                    f"status={row.validation_status!r} is immutable in live mode"
                )
                skipped_immutable_count += 1

        if not is_no_op:
            changes.append(change_record)

    if not opts.dry_run and applied_count > 0:
        await db.flush()
        await db.commit()

    summary = _summarize_changes(changes, total_scanned=len(rows))
    summary["applied"] = applied_count
    summary["skipped_immutable"] = skipped_immutable_count

    return {
        "jurisdiction_id": str(jurisdiction_id),
        "jurisdiction_name": juris.name,
        "dry_run": opts.dry_run,
        "scanned": len(rows),
        "filter": {
            "only_status": list(opts.only_status) if opts.only_status else None,
            "stale_only": opts.stale_only,
            "max_rows": opts.max_rows,
            "source_ids": [str(s) for s in opts.source_ids] if opts.source_ids else None,
        },
        "summary": summary,
        "changes": changes,
        "errors": errors,
    }


async def score_health(
    jurisdiction_id: uuid.UUID | None,
    db: AsyncSession,
    *,
    max_age_days: int | None = _DEFAULT_MAX_AGE_DAYS,
) -> dict[str, Any]:
    """No-probe summary of rescore eligibility for one jurisdiction (or
    all when `jurisdiction_id` is None).

    Cheap — pure DB read + per-row pure-function predicate. No upstream
    HTTP calls. Designed to power a periodic dashboard poll without
    burning ArcGIS quota.

    Returns:
      {
        jurisdictions: [
          {
            jurisdiction_id, jurisdiction_name,
            scoring_version_current,
            counts: {
              total, eligible_total, not_eligible,
              by_reason: {scoring_version_lower: N, ...},
            },
            jurisdiction_bbox_updated_at: <iso>,
          },
          ...
        ],
        scoring_version_current: SCORING_VERSION,
      }
    """
    rows = await _load_rows_for_health(jurisdiction_id, db)
    juris_cache: dict[uuid.UUID, Jurisdiction] = {}
    denylist = await _fetch_rejected_endpoints(db)
    now = datetime.now(timezone.utc)

    # Group rows by jurisdiction so we can resolve each jurisdiction's
    # bbox-updated-at exactly once.
    per_juris: dict[uuid.UUID, list[ZoningSource]] = {}
    for r in rows:
        if r.jurisdiction_id is None:
            continue
        per_juris.setdefault(r.jurisdiction_id, []).append(r)

    results: list[dict[str, Any]] = []
    for jid, jrows in per_juris.items():
        juris = juris_cache.get(jid) or await db.get(Jurisdiction, jid)
        if juris is None:
            continue
        juris_cache[jid] = juris
        bbox_ts = getattr(juris, "bbox_updated_at", None) or juris.last_indexed_at

        by_reason: dict[str, int] = {k: 0 for k in ELIGIBILITY_REASONS}
        eligible_total = 0
        for r in jrows:
            verdict = rescore_eligibility(
                r,
                current_version=SCORING_VERSION,
                jurisdiction_bbox_updated_at=bbox_ts,
                denylist=denylist,
                max_age_days=max_age_days,
                now=now,
            )
            if verdict is not None:
                by_reason[verdict["reason"]] += 1
                eligible_total += 1

        results.append({
            "jurisdiction_id": str(jid),
            "jurisdiction_name": juris.name,
            "scoring_version_current": SCORING_VERSION,
            "counts": {
                "total": len(jrows),
                "eligible_total": eligible_total,
                "not_eligible": len(jrows) - eligible_total,
                "by_reason": by_reason,
            },
            "jurisdiction_bbox_updated_at": (
                bbox_ts.isoformat() if bbox_ts else None
            ),
        })

    # Sort by eligible_total desc so the operator sees the biggest queues first.
    results.sort(key=lambda r: r["counts"]["eligible_total"], reverse=True)

    return {
        "scoring_version_current": SCORING_VERSION,
        "max_age_days": max_age_days,
        "jurisdictions": results,
    }


async def _load_rows_for_health(
    jurisdiction_id: uuid.UUID | None, db: AsyncSession,
) -> list[ZoningSource]:
    q = select(ZoningSource)
    if jurisdiction_id is not None:
        q = q.where(ZoningSource.jurisdiction_id == jurisdiction_id)
    return list((await db.execute(q)).scalars().all())


async def rollback_rescores(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession,
    snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    """Restore (confidence_score, confidence_label, confidence_breakdown,
    reasons) on each row from a prior `changes[].before` snapshot.

    `snapshots` is a list of dicts shaped like the `before` payload returned
    by `rescore_stale_sources`, each carrying the `source_id` field plus
    the four fields to restore.

    Like rescore: never touches validation_status, rejected_reason,
    notes, or last_verified_at. Only rows whose status is currently
    `pending` or `needs_review` are restored — a row that has been
    verified or rejected after the rescore should not be quietly
    overwritten by a stale snapshot.
    """
    restored: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    not_found: list[str] = []
    now = datetime.now(timezone.utc)

    for snap in snapshots:
        sid = snap.get("source_id")
        if not sid:
            continue
        try:
            row_id = uuid.UUID(sid) if isinstance(sid, str) else sid
        except (ValueError, AttributeError):
            not_found.append(str(sid))
            continue
        row = await db.get(ZoningSource, row_id)
        if row is None or row.jurisdiction_id != jurisdiction_id:
            not_found.append(str(sid))
            continue
        if row.validation_status not in _MUTABLE_STATUSES:
            skipped.append({
                "source_id": str(row.id),
                "reason": f"status={row.validation_status!r} is immutable",
            })
            continue
        row.confidence_score = snap.get("confidence_score")
        row.confidence_label = snap.get("confidence_label")
        row.confidence_breakdown = snap.get("confidence_breakdown")
        row.reasons = snap.get("reasons")
        row.updated_at = now
        restored.append({"source_id": str(row.id)})

    if restored:
        await db.flush()
        await db.commit()

    return {
        "jurisdiction_id": str(jurisdiction_id),
        "restored": len(restored),
        "skipped": skipped,
        "not_found": not_found,
    }


# ───────────────────────── internals ─────────────────────────────────────────

async def _load_target_rows(
    jurisdiction_id: uuid.UUID,
    opts: RescoreOptions,
    db: AsyncSession,
) -> list[ZoningSource]:
    """Return rows matching the filter. `stale_only` is enforced in Python
    rather than SQL because confidence_breakdown is JSONB and the
    'no bbox_overlap_* key' check is awkward to express portably."""
    q = select(ZoningSource).where(ZoningSource.jurisdiction_id == jurisdiction_id)
    if opts.only_status:
        q = q.where(ZoningSource.validation_status.in_(opts.only_status))
    if opts.source_ids:
        q = q.where(ZoningSource.id.in_(opts.source_ids))
    q = q.order_by(ZoningSource.confidence_score.desc().nulls_last())
    rows = (await db.execute(q)).scalars().all()
    if opts.stale_only:
        rows = [r for r in rows if not _has_bbox_overlap_component(r.confidence_breakdown)]
    return list(rows)


def _has_bbox_overlap_component(breakdown: dict | None) -> bool:
    if not isinstance(breakdown, dict):
        return False
    return any(k in breakdown for k in _BBOX_OVERLAP_COMPONENT_NAMES)


# ─── Re-score eligibility ────────────────────────────────────────────────────
#
# A row is eligible for rescore when any of the following is true:
#
#   - SCORING_VERSION moved past the version implied by the row's stored
#     breakdown markers. We never store the version explicitly (no migration);
#     instead we infer from which marker components appear in the breakdown.
#   - The jurisdiction's bbox was refreshed AFTER the row was last scored
#     (Component F was computed against a stale bbox).
#   - The row's URL is now in the denylist but the breakdown doesn't carry
#     the `denylist_rejected` component — the operator's reject decision
#     hasn't been reflected in the score.
#   - The row's `updated_at` is older than the max_age cap (default 90d).
#
# Returns None when the row is NOT eligible — the caller skips it. Returns
# a short stable reason code + human-readable text when it IS eligible.
# The operator dashboard surfaces both fields so the queue can be filtered
# by reason ("show me only rows stale because the bbox refreshed").

ELIGIBILITY_REASONS = (
    "scoring_version_lower",
    "jurisdiction_bbox_refreshed",
    "denylist_url_not_reflected",
    "age_exceeds_max",
)


def infer_row_scoring_version(breakdown: dict | None) -> int:
    """Highest scoring version whose marker components appear in this row's
    breakdown. Pre-v2 rows lack Component F and return version 1; rows
    persisted by v2+ carry one of the bbox_overlap_* keys. Future
    versions extend SCORING_VERSION_MARKERS the same way."""
    if not isinstance(breakdown, dict):
        return 1
    inferred = 1
    for version, markers in SCORING_VERSION_MARKERS.items():
        if any(k in breakdown for k in markers):
            inferred = max(inferred, version)
    return inferred


def rescore_eligibility(
    row: ZoningSource,
    *,
    current_version: int = SCORING_VERSION,
    jurisdiction_bbox_updated_at: datetime | None = None,
    denylist: set[str] | None = None,
    max_age_days: int | None = _DEFAULT_MAX_AGE_DAYS,
    now: datetime | None = None,
) -> dict[str, str] | None:
    """Return the eligibility verdict for one row, or None when not eligible.

    Pure function — no I/O. The caller is responsible for batching the
    inputs (denylist, jurisdiction_bbox_updated_at) once per jurisdiction
    so the per-row cost is constant.

    Verdict shape: ``{"reason": "<code>", "detail": "<human text>"}``.
    Use the codes in `ELIGIBILITY_REASONS` for downstream filtering.
    """
    # 1. Scoring-version drift — strongest reason, take it first.
    row_version = infer_row_scoring_version(row.confidence_breakdown)
    if row_version < current_version:
        return {
            "reason": "scoring_version_lower",
            "detail": f"row scored under v{row_version}, current is v{current_version}",
        }

    # 2. Jurisdiction bbox refreshed after the row was scored — Component F
    #    was computed against a stale jurisdiction bbox and may now be wrong.
    if (
        jurisdiction_bbox_updated_at is not None
        and row.updated_at is not None
        and jurisdiction_bbox_updated_at > row.updated_at
    ):
        return {
            "reason": "jurisdiction_bbox_refreshed",
            "detail": (
                f"jurisdiction bbox refreshed {jurisdiction_bbox_updated_at.isoformat()}; "
                f"row last scored {row.updated_at.isoformat()}"
            ),
        }

    # 3. Denylist URL not reflected — operator rejected this endpoint
    #    somewhere else but Component D was never applied here.
    if (
        denylist
        and row.zoning_endpoint in denylist
        and not _breakdown_has_denylist_penalty(row.confidence_breakdown)
    ):
        return {
            "reason": "denylist_url_not_reflected",
            "detail": "endpoint is in cross-jurisdiction denylist; row missing -80 penalty",
        }

    # 4. Stale by age — last resort signal. Default 90d so we don't churn
    #    healthy rows; operator can pass max_age_days=None to disable.
    if max_age_days is not None and row.updated_at is not None:
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=max_age_days)
        if row.updated_at < cutoff:
            return {
                "reason": "age_exceeds_max",
                "detail": (
                    f"row last scored {row.updated_at.isoformat()}, "
                    f">{max_age_days}d ago"
                ),
            }

    return None


def _breakdown_has_denylist_penalty(breakdown: dict | None) -> bool:
    if not isinstance(breakdown, dict):
        return False
    return "denylist_rejected" in breakdown


async def _probe_rows(
    rows: list[ZoningSource],
    jurisdiction_bbox: list[float] | None,
    concurrency: int,
    http_client: httpx.AsyncClient | None,
) -> list[dict[str, Any] | None]:
    sem = asyncio.Semaphore(concurrency)

    async def _one(row: ZoningSource, client: httpx.AsyncClient) -> dict[str, Any] | None:
        if not row.zoning_endpoint:
            return None
        async with sem:
            try:
                return await spatial_check_for_url(
                    row.zoning_endpoint, jurisdiction_bbox, client=client,
                )
            except Exception as exc:
                logger.warning("spatial probe failed for %s: %r", row.id, exc)
                return {"verdict": "error", "error": repr(exc)[:200]}

    own_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=15.0, follow_redirects=True)
    try:
        return await asyncio.gather(*[_one(r, client) for r in rows])
    finally:
        if own_client:
            await client.aclose()


def _recompute_row(
    *,
    row: ZoningSource,
    probe: dict[str, Any] | None,
    jurisdiction: Jurisdiction,
    name_tokens: dict,
    denylist: set[str],
) -> dict[str, Any]:
    """Replay `_score_candidate` against the row's persisted static fields
    + the live probe's bbox_overlap_ratio. Returns an `after` dict
    shaped like the `before` snapshot."""
    title = row.title or ""
    title_lc = title.lower()
    pos_hits = [k for k in _ZONING_KEYWORDS_POSITIVE if k in title_lc]
    neg_hits = [k for k in _ZONING_KEYWORDS_NEGATIVE if k in title_lc]
    name_signals = _name_match_signals(title, name_tokens)

    field_matches = row.field_matches if isinstance(row.field_matches, list) else []
    bbox_overlap_ratio = (probe or {}).get("bbox_overlap_ratio")

    score, components = _score_candidate(
        title=title,
        url=row.zoning_endpoint or "",
        pos_hits=pos_hits,
        neg_hits=neg_hits,
        geometry_type=row.geometry_type,
        feature_count=row.feature_count,
        field_matches=field_matches,
        bbox_overlap_ratio=bbox_overlap_ratio,
        name_signals=name_signals,
        jurisdiction=jurisdiction,
        denylist=denylist,
    )
    reasons = [c.reason for c in components if c.reason]
    breakdown = {c.name: c.delta for c in components}

    # confidence_label: preserve operator labels (verified/rejected);
    # otherwise recompute from the new score the same way discovery does.
    if row.validation_status == "verified":
        label = "verified"
    elif row.validation_status == "rejected":
        label = "rejected"
    elif score >= _QUEUE_THRESHOLD:
        label = "discovered"
    else:
        label = "discovered_low"

    return {
        "after": {
            "confidence_score": score,
            "confidence_label": label,
            "confidence_breakdown": breakdown,
            "reasons": reasons,
        },
    }


def _snapshot(row: ZoningSource) -> dict[str, Any]:
    """Capture the four fields rescore touches, in the shape the rollback
    endpoint accepts back."""
    return {
        "source_id": str(row.id),
        "confidence_score": row.confidence_score,
        "confidence_label": row.confidence_label,
        "confidence_breakdown": row.confidence_breakdown,
        "reasons": row.reasons,
    }


def _crosses_threshold(before: int | None, after: int | None, threshold: int) -> str | None:
    """Return 'down' / 'up' if the score crossed `threshold` in either
    direction, else None. Operator uses this to find rows that just
    fell out of the high-confidence triage queue."""
    if before is None or after is None:
        return None
    if before >= threshold > after:
        return "down"
    if before < threshold <= after:
        return "up"
    return None


def _bucket_delta(d: int) -> str:
    if d <= -50: return "≤-50"
    if d <= -20: return "-49..-20"
    if d < 0:    return "-19..-1"
    if d == 0:   return "0"
    if d < 20:   return "1..19"
    if d < 50:   return "20..49"
    return "≥50"


def _summarize_changes(
    changes: list[dict[str, Any]],
    *,
    total_scanned: int,
) -> dict[str, Any]:
    decreases = sum(1 for c in changes if c["delta"] < 0)
    increases = sum(1 for c in changes if c["delta"] > 0)
    newly_below = sum(1 for c in changes if c["crosses_threshold_70"] == "down")
    newly_above = sum(1 for c in changes if c["crosses_threshold_70"] == "up")
    new_disjoint = sum(1 for c in changes if c["live_verdict"] == "disjoint")
    no_change = total_scanned - len(changes)

    delta_buckets: dict[str, int] = {}
    for c in changes:
        b = _bucket_delta(c["delta"])
        delta_buckets[b] = delta_buckets.get(b, 0) + 1

    return {
        "no_change": no_change,
        "changed": len(changes),
        "score_decreased": decreases,
        "score_increased": increases,
        "newly_below_threshold_70": newly_below,
        "newly_above_threshold_70": newly_above,
        "live_verdict_disjoint": new_disjoint,
        "score_delta_distribution": delta_buckets,
    }


def _empty_response(
    juris: Jurisdiction,
    opts: RescoreOptions,
    *,
    scanned: int,
) -> dict[str, Any]:
    return {
        "jurisdiction_id": str(juris.id),
        "jurisdiction_name": juris.name,
        "dry_run": opts.dry_run,
        "scanned": scanned,
        "filter": {
            "only_status": list(opts.only_status) if opts.only_status else None,
            "stale_only": opts.stale_only,
            "max_rows": opts.max_rows,
            "source_ids": [str(s) for s in opts.source_ids] if opts.source_ids else None,
        },
        "summary": {
            "no_change": 0, "changed": 0,
            "score_decreased": 0, "score_increased": 0,
            "newly_below_threshold_70": 0, "newly_above_threshold_70": 0,
            "live_verdict_disjoint": 0, "score_delta_distribution": {},
            "applied": 0, "skipped_immutable": 0,
        },
        "changes": [],
        "errors": [],
    }
