"""Municipality remediation — turns health gaps into an ordered plan of
operator actions.

For each muni-health gap pattern, this module returns one or more
`RemediationStep` records: a stable `action_code`, the rationale for
including it, the exact endpoint call to make (method + path + body),
the CLI equivalent, and step dependencies.

No mutation. No automation. The plan is *advice* — the operator runs it.

Action codes are stable IDs (don't rename without bumping a dashboard
contract). Dependencies are by step number within a single muni plan
(1-indexed), so the operator can pipe the plan into a worksheet and
work top-down.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.jurisdiction import Jurisdiction
from app.models.zoning_source import ZoningSource
from app.services.municipality_health import jurisdiction_municipalities_health

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Escalation thresholds — when does a band stop being self-serve and
# need engineer-level attention?
# ──────────────────────────────────────────────────────────────────────

# A `broken` muni whose remediation plan has > N steps OR includes
# `audit_spatial_sources` is treated as engineer-level. Operators run
# self-serve steps; engineers handle ambiguous re-discovery.
ESCALATION_MAX_BROKEN_STEPS = 4
ESCALATION_REQUIRES_ENGINEER_ACTION_CODES = frozenset({"audit_spatial_sources"})


# ──────────────────────────────────────────────────────────────────────
# Action library
# ──────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class RemediationStep:
    step: int
    action_code: str
    label: str
    rationale: str
    severity: str                        # "must" | "should" | "consider"
    command: dict[str, Any]              # {method, path, body, query?}
    cli_hint: str | None
    dependencies: list[int] = field(default_factory=list)


@dataclass(slots=True)
class RemediationPlan:
    municipality: str | None
    trustworthiness: str
    gaps: list[str]
    steps: list[RemediationStep]
    needs_operator_input: list[str]
    escalate_to_engineer: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "municipality": self.municipality,
            "trustworthiness": self.trustworthiness,
            "gaps": list(self.gaps),
            "steps": [asdict(s) for s in self.steps],
            "needs_operator_input": list(self.needs_operator_input),
            "escalate_to_engineer": self.escalate_to_engineer,
        }


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


async def jurisdiction_municipalities_remediation(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession,
    *,
    municipality: str | None = None,
) -> dict[str, Any]:
    """For each muni in the jurisdiction (or just the named one), join its
    health snapshot with a remediation plan."""
    health = await jurisdiction_municipalities_health(
        jurisdiction_id, db, municipality=municipality,
    )
    if "error" in health:
        return health

    juris = await db.get(Jurisdiction, jurisdiction_id)
    is_county_with_munis = await _county_uses_per_town_sources(jurisdiction_id, db)

    plans: list[dict[str, Any]] = []
    for muni in health.get("municipalities") or []:
        muni_name = muni.get("municipality")
        sources = await _load_sources_for_muni(jurisdiction_id, muni_name, db)
        plan = build_remediation_plan(
            jurisdiction_id=jurisdiction_id,
            jurisdiction_name=juris.name if juris else "",
            muni=muni,
            sources=sources,
            is_county_with_munis=is_county_with_munis,
        )
        plans.append({**muni, "remediation": plan.to_dict()})

    # Roll up actionability so the dashboard can show a single "next muni
    # to touch" link without iterating client-side.
    next_actionable = next(
        (
            p for p in plans
            if (p["remediation"]["steps"] and not p["remediation"]["escalate_to_engineer"])
        ),
        None,
    )

    return {
        "jurisdiction_id": str(jurisdiction_id),
        "jurisdiction_name": juris.name if juris else None,
        "is_county_with_munis": is_county_with_munis,
        "municipality_count": len(plans),
        "band_counts": health.get("band_counts"),
        "thresholds": health.get("thresholds"),
        "next_actionable_municipality": (
            next_actionable.get("municipality") if next_actionable else None
        ),
        "municipalities": plans,
    }


# ──────────────────────────────────────────────────────────────────────
# Gap → action mapping (the actual playbook)
# ──────────────────────────────────────────────────────────────────────

# Gap patterns and the canonical action_code each implies. Order in the
# list = sequence intent (the build_remediation_plan loop emits steps in
# this order, dropping duplicates).
_GAP_PATTERNS: tuple[tuple[re.Pattern, str, str], ...] = (
    (re.compile(r"extents? .*overlap only \d+%.*wrong location",
                re.IGNORECASE),
     "reject_wrong_source",
     "must"),
    (re.compile(r"districts ingested .* 0|districts ingested for this muni: 0",
                re.IGNORECASE),
     "discover_new_source",
     "must"),
    (re.compile(r"invalid PostGIS geometry", re.IGNORECASE),
     "replace_districts",
     "must"),
    (re.compile(r"spatial join likely failed|carry zoning_code", re.IGNORECASE),
     "respatial_join",
     "should"),
    (re.compile(r"overlap a sibling", re.IGNORECASE),
     "replace_districts",
     "should"),
    (re.compile(r"only \d+ parcels", re.IGNORECASE),
     "backfill_parcel_city",
     "should"),
    (re.compile(r"only \d+ distinct district polygons", re.IGNORECASE),
     "audit_spatial_sources",
     "should"),
    (re.compile(r"zone_class.*matrix coverage is shallow", re.IGNORECASE),
     "bootstrap_matrix",
     "consider"),
    (re.compile(r"zone codes on parcels not present on any district",
                re.IGNORECASE),
     "audit_orphan_zone_codes",
     "consider"),
)


def build_remediation_plan(
    *,
    jurisdiction_id: uuid.UUID,
    jurisdiction_name: str,
    muni: dict[str, Any],
    sources: list[ZoningSource],
    is_county_with_munis: bool,
) -> RemediationPlan:
    """Map a muni's gaps to a sequenced remediation plan. Pure once the
    DB context is loaded — easy to unit-test."""
    band = muni.get("trustworthiness", "operational")
    gaps = list(muni.get("gaps") or [])
    muni_name = muni.get("municipality")

    # Operational munis don't need a plan — EXCEPT when iter-6 confidence
    # flags them as low. False-operational munis get a single
    # `review_confidence_flags` step so the operator's queue isn't silently
    # contaminated.
    if band == "operational":
        confidence = muni.get("confidence", "high")
        caveats = list(muni.get("caveats") or [])
        if confidence == "low" and caveats:
            return RemediationPlan(
                municipality=muni_name, trustworthiness=band,
                gaps=gaps,
                steps=[RemediationStep(
                    step=1,
                    action_code="review_confidence_flags",
                    label=f"Review confidence flags for {muni_name or jurisdiction_name}",
                    rationale=(
                        "Primary metrics say operational but secondary signals "
                        "suggest the data may not be trustworthy: "
                        + "; ".join(caveats)
                    ),
                    severity="should",
                    command={
                        "method": "GET",
                        "path": f"/api/jurisdictions/{jurisdiction_id}/_municipalities-health",
                        "query": {"municipality": muni_name} if muni_name else None,
                        "body": None,
                    },
                    cli_hint=(
                        f"python scripts/municipality_health.py {jurisdiction_id} "
                        + (f"--muni '{muni_name}'" if muni_name else "")
                    ),
                )],
                needs_operator_input=[
                    f"operator must judge whether the secondary flags reflect "
                    f"genuine data or expected muni characteristics "
                    f"({', '.join(muni.get('secondary_flags') or [])})"
                ],
                escalate_to_engineer=False,
            )
        return RemediationPlan(
            municipality=muni_name, trustworthiness=band,
            gaps=gaps, steps=[], needs_operator_input=[],
            escalate_to_engineer=False,
        )

    # Map gaps → action_codes, preserving _GAP_PATTERNS order, dedup.
    action_codes: list[tuple[str, str, str]] = []  # (code, severity, gap_text)
    seen: set[str] = set()
    for gap in gaps:
        for pattern, code, severity in _GAP_PATTERNS:
            if pattern.search(gap) and code not in seen:
                action_codes.append((code, severity, gap))
                seen.add(code)
                break

    # Empty band has its own minimal plan.
    if band == "empty":
        action_codes = [("discover_new_source", "must", "no parcels or districts")]

    # Expand follow-on chains so the operator sees the complete repair
    # sequence, not just the first move. Each rule fires once: a gap that
    # demands rejection implies discovery, then verify, then ingest, then
    # re-spatial-join — running the endpoint again after each completed
    # step would yield this list incrementally; chain expansion shows it
    # all up-front.
    # Chain expansion stops at operator-judgment gates: after discovery
    # the operator must review candidates before we can recommend a
    # verify. Once they verify, the next call to this endpoint sees a
    # verified row and emits the ingest+respatial steps automatically.
    # Deterministic continuations (verify→ingest→respatial_join,
    # replace→respatial_join) DO chain so the operator sees the full
    # follow-through without re-querying after each step.
    _CHAINS = {
        "reject_wrong_source":  ["discover_new_source"],
        # Intentionally no edge from discover → verify (operator review gate).
        "verify_top_candidate": ["ingest_verified_source"],
        "ingest_verified_source": ["respatial_join"],
        "replace_districts":    ["respatial_join"],
    }
    queue = [c[0] for c in action_codes]
    while queue:
        cur = queue.pop(0)
        for follow in _CHAINS.get(cur, []):
            if follow not in seen:
                # Inherit the predecessor's severity for chained must-do
                # rejects; chained from a 'should' stays 'should'.
                inherited = next(
                    (sev for code, sev, _ in action_codes if code == cur), "should",
                )
                action_codes.append((follow, inherited, f"chained from {cur}"))
                seen.add(follow)
                queue.append(follow)

    # Resolve each action_code to a concrete RemediationStep.
    steps: list[RemediationStep] = []
    needs_input: list[str] = []
    for code, severity, gap in action_codes:
        step = _materialize_step(
            code=code, severity=severity, gap=gap,
            step_number=len(steps) + 1,
            jurisdiction_id=jurisdiction_id, jurisdiction_name=jurisdiction_name,
            muni_name=muni_name, sources=sources,
            is_county_with_munis=is_county_with_munis,
            needs_input=needs_input,
        )
        if step is not None:
            steps.append(step)

    # Auto-sequence: respatial_join always follows replace_districts / ingest;
    # verify follows discover; ingest follows verify.
    steps = _link_dependencies(steps)

    escalate = (
        band == "broken" and (
            len(steps) > ESCALATION_MAX_BROKEN_STEPS
            or any(s.action_code in ESCALATION_REQUIRES_ENGINEER_ACTION_CODES for s in steps)
        )
    )

    return RemediationPlan(
        municipality=muni_name, trustworthiness=band,
        gaps=gaps, steps=steps,
        needs_operator_input=needs_input,
        escalate_to_engineer=escalate,
    )


# ──────────────────────────────────────────────────────────────────────
# Step materializers — one branch per action_code
# ──────────────────────────────────────────────────────────────────────

def _materialize_step(
    *,
    code: str, severity: str, gap: str, step_number: int,
    jurisdiction_id: uuid.UUID, jurisdiction_name: str,
    muni_name: str | None, sources: list[ZoningSource],
    is_county_with_munis: bool,
    needs_input: list[str],
) -> RemediationStep | None:
    jid = str(jurisdiction_id)
    muni_label = muni_name or jurisdiction_name

    if code == "reject_wrong_source":
        verified = _find_source(sources, status="verified")
        if verified is None:
            # Reject doesn't apply if there's no verified row; fall through
            # to discover instead.
            return _materialize_step(
                code="discover_new_source", severity="must", gap=gap,
                step_number=step_number, jurisdiction_id=jurisdiction_id,
                jurisdiction_name=jurisdiction_name, muni_name=muni_name,
                sources=sources, is_county_with_munis=is_county_with_munis,
                needs_input=needs_input,
            )
        return RemediationStep(
            step=step_number, action_code="reject_wrong_source",
            label=f"Reject the verified source for {muni_label} — it covers the wrong location",
            rationale=(
                "The verified source's extent is spatially disjoint from the muni's "
                "parcels. Reject it before re-discovering; the URL is added to the "
                "cross-jurisdiction denylist so it can't be re-verified by mistake."
            ),
            severity=severity,
            command={
                "method": "POST",
                "path": f"/api/jurisdictions/{jid}/_sources/{verified.id}/_review",
                "body": {
                    "action": "reject",
                    "rejected_reason": "muni-health: extent disjoint from parcels",
                },
            },
            cli_hint=(
                f"curl -X POST .../jurisdictions/{jid}/_sources/{verified.id}/_review "
                "-H 'content-type: application/json' "
                "-d '{\"action\":\"reject\",\"rejected_reason\":\"muni-health: extent disjoint\"}'"
            ),
        )

    if code == "discover_new_source":
        # Discovery is followed by an operator-review gate — surface that
        # in needs_operator_input so the plan reader knows the chain
        # doesn't continue automatically.
        needs_input.append(
            f"after discovery, review /_sources?status=pending for {muni_label!r} "
            "and verify the top candidate before the next remediation step"
        )
        if is_county_with_munis and muni_name:
            return RemediationStep(
                step=step_number, action_code="discover_new_source",
                label=f"Discover per-town zoning sources for {muni_name}",
                rationale=(
                    "No verified source covers this town. Re-running per-municipal "
                    "discovery surfaces fresh Hub candidates; v2 scoring + the "
                    "denylist will exclude previously-rejected URLs."
                ),
                severity=severity,
                command={
                    "method": "POST",
                    "path": f"/api/jurisdictions/{jid}/_discover-municipal-zoning",
                    "body": {"municipality_names": [muni_name]},
                },
                cli_hint=(
                    f"curl -X POST .../jurisdictions/{jid}/_discover-municipal-zoning "
                    "-H 'content-type: application/json' "
                    f"-d '{{\"municipality_names\":[\"{muni_name}\"]}}'"
                ),
            )
        # City-jurisdiction (no per-muni Hub fan-out).
        return RemediationStep(
            step=step_number, action_code="discover_new_source",
            label=f"Re-run discovery for {jurisdiction_name}",
            rationale=(
                "No verified source for this jurisdiction. Re-discover from "
                "ArcGIS Hub; the current scoring + denylist will exclude prior FPs."
            ),
            severity=severity,
            command={
                "method": "POST",
                "path": f"/api/jurisdictions/{jid}/_discover-zoning",
                "body": {},
            },
            cli_hint=f"curl -X POST .../jurisdictions/{jid}/_discover-zoning",
        )

    if code == "verify_top_candidate":
        top = _find_source(sources, status="pending", min_confidence=70)
        if top is None:
            needs_input.append(
                f"no high-confidence pending source for {muni_label!r}; "
                "operator must review /_sources or re-discover"
            )
            return None
        return RemediationStep(
            step=step_number, action_code="verify_top_candidate",
            label=f"Verify the top discovered candidate for {muni_label}",
            rationale=(
                f"Pending candidate at score {top.confidence_score} looks legitimate. "
                "Verifying flips its status; the next step ingests it."
            ),
            severity=severity,
            command={
                "method": "POST",
                "path": f"/api/jurisdictions/{jid}/_sources/{top.id}/_review",
                "body": {"action": "verify"},
            },
            cli_hint=(
                f"curl -X POST .../jurisdictions/{jid}/_sources/{top.id}/_review "
                f"-d '{{\"action\":\"verify\"}}'"
            ),
        )

    if code == "ingest_verified_source":
        verified = _find_source(sources, status="verified")
        if verified is None:
            needs_input.append(
                f"no verified source for {muni_label!r}; verify one before ingest"
            )
            return None
        if is_county_with_munis:
            return RemediationStep(
                step=step_number, action_code="ingest_verified_source",
                label=f"Ingest verified source into {muni_label}",
                rationale=(
                    "Verified source hasn't been ingested yet. The endpoint runs "
                    "the pre-flight bbox check and writes zoning_districts + spatial-"
                    "joins parcels."
                ),
                severity=severity,
                command={
                    "method": "POST",
                    "path": f"/api/jurisdictions/{jid}/_ingest-municipal-zoning",
                    "body": {"source_ids": [str(verified.id)]},
                },
                cli_hint=(
                    f"curl -X POST .../jurisdictions/{jid}/_ingest-municipal-zoning "
                    f"-d '{{\"source_ids\":[\"{verified.id}\"]}}'"
                ),
            )
        return RemediationStep(
            step=step_number, action_code="ingest_verified_source",
            label=f"Backfill verified source into {jurisdiction_name}",
            rationale="Verified source exists; backfill ingests districts + spatial-joins parcels.",
            severity=severity,
            command={
                "method": "POST",
                "path": f"/api/jurisdictions/{jid}/_backfill-zoning",
                "query": {"zoning_url": verified.zoning_endpoint or "", "replace": "true"},
                "body": {},
            },
            cli_hint=(
                f"curl -X POST '.../jurisdictions/{jid}/_backfill-zoning?"
                f"zoning_url={verified.zoning_endpoint}&replace=true'"
            ),
        )

    if code == "respatial_join":
        return RemediationStep(
            step=step_number, action_code="respatial_join",
            label=f"Re-run spatial join for {jurisdiction_name}",
            rationale=(
                "Districts exist but parcels don't carry zoning_code. Re-running "
                "backfill with spatial_join=true reapplies the polygon→parcel "
                "overlay without re-downloading the layer."
            ),
            severity=severity,
            command={
                "method": "POST",
                "path": f"/api/jurisdictions/{jid}/_backfill-zoning",
                "query": {"spatial_join": "true", "replace": "false"},
                "body": {},
            },
            cli_hint=(
                f"curl -X POST '.../jurisdictions/{jid}/_backfill-zoning"
                "?spatial_join=true&replace=false'"
            ),
        )

    if code == "replace_districts":
        verified = _find_source(sources, status="verified")
        if verified is None:
            needs_input.append(
                f"need a verified source for {muni_label!r} before re-ingest"
            )
            return None
        return RemediationStep(
            step=step_number, action_code="replace_districts",
            label=f"Replace zoning_districts for {jurisdiction_name}",
            rationale=(
                "Districts have invalid geometry or duplicate polygons. "
                "Re-ingesting with replace=true drops the current set and "
                "re-fetches from the verified source."
            ),
            severity=severity,
            command={
                "method": "POST",
                "path": f"/api/jurisdictions/{jid}/_backfill-zoning",
                "query": {
                    "zoning_url": verified.zoning_endpoint or "",
                    "replace": "true",
                    "spatial_join": "true",
                },
                "body": {},
            },
            cli_hint=(
                f"curl -X POST '.../jurisdictions/{jid}/_backfill-zoning"
                f"?zoning_url={verified.zoning_endpoint}&replace=true&spatial_join=true'"
            ),
        )

    if code == "backfill_parcel_city":
        return RemediationStep(
            step=step_number, action_code="backfill_parcel_city",
            label=f"Backfill parcels.city for {jurisdiction_name}",
            rationale=(
                "Too few parcels are tagged to this muni. Either parcel ingest "
                "ran without city tagging, or the parcel source uses a different "
                "muni-name spelling. Run the backfill script to reconcile."
            ),
            severity=severity,
            command={
                "method": "POST",
                "path": f"/api/admin/_backfill-nj-parcel-city",
                "body": {"jurisdiction_id": jid},
            },
            cli_hint=f"python scripts/backfill_parcel_city.py --jurisdiction {jid}",
        )

    if code == "audit_spatial_sources":
        return RemediationStep(
            step=step_number, action_code="audit_spatial_sources",
            label=f"Audit zoning_sources for {jurisdiction_name}",
            rationale=(
                "Ambiguous failure — too few districts, or a verified source's "
                "spatial-check verdict has drifted. Use the audit to inspect "
                "the source × verdict cross-tab and decide whether to re-verify "
                "or re-discover."
            ),
            severity=severity,
            command={
                "method": "GET",
                "path": f"/api/jurisdictions/{jid}/_spatial-audit",
                "body": None,
            },
            cli_hint=f"python scripts/spatial_audit.py {jid}",
        )

    if code == "bootstrap_matrix":
        return RemediationStep(
            step=step_number, action_code="bootstrap_matrix",
            label=f"Bootstrap zone_use_matrix for {jurisdiction_name}",
            rationale=(
                "Most parcels have zoning_code but no zone_class — the matrix "
                "for this jurisdiction hasn't been populated. Bootstrap from "
                "the ordinance parser or the manual matrix templates."
            ),
            severity=severity,
            command={
                "method": "POST",
                "path": f"/api/ordinances/{jid}/parse",
                "body": {},
            },
            cli_hint=(
                "see backend/scripts/setup_<city>.py templates "
                "or POST /api/ordinances/{id}/parse with an ordinance URL"
            ),
        )

    if code == "audit_orphan_zone_codes":
        return RemediationStep(
            step=step_number, action_code="audit_orphan_zone_codes",
            label=f"Audit orphan zone codes for {jurisdiction_name}",
            rationale=(
                "Some parcel.zoning_code values aren't on any zoning_district. "
                "Either the codes came from the parcel source (Regrid/assessor) "
                "rather than the spatial join, or the district layer is missing "
                "those codes. Matrix bind will miss these parcels."
            ),
            severity=severity,
            command={
                "method": "GET",
                "path": f"/api/jurisdictions/{jid}/parcels/zone-summary",
                "body": None,
            },
            cli_hint=(
                "compare GET /jurisdictions/{id}/parcels/zone-summary "
                "against GET /jurisdictions/{id}/zoning-districts"
            ),
        )

    logger.debug("unknown remediation action_code: %r", code)
    return None


def _link_dependencies(steps: list[RemediationStep]) -> list[RemediationStep]:
    """Wire `dependencies` so the operator knows what must run before what.
    Mutates the list in place; returns it for chaining."""
    by_code: dict[str, int] = {s.action_code: s.step for s in steps}

    def _dep(step: RemediationStep, predecessor_code: str) -> None:
        n = by_code.get(predecessor_code)
        if n is not None and n < step.step:
            step.dependencies.append(n)

    for s in steps:
        if s.action_code == "verify_top_candidate":
            _dep(s, "discover_new_source")
        elif s.action_code == "ingest_verified_source":
            _dep(s, "verify_top_candidate")
            _dep(s, "discover_new_source")
        elif s.action_code == "respatial_join":
            _dep(s, "ingest_verified_source")
            _dep(s, "replace_districts")
        elif s.action_code == "replace_districts":
            _dep(s, "reject_wrong_source")
        elif s.action_code == "discover_new_source":
            _dep(s, "reject_wrong_source")

    return steps


# ──────────────────────────────────────────────────────────────────────
# Loaders — small helpers around the existing zoning_sources table.
# ──────────────────────────────────────────────────────────────────────

async def _load_sources_for_muni(
    jurisdiction_id: uuid.UUID,
    municipality_name: str | None,
    db: AsyncSession,
) -> list[ZoningSource]:
    q = select(ZoningSource).where(ZoningSource.jurisdiction_id == jurisdiction_id)
    if municipality_name is not None:
        q = q.where(ZoningSource.municipality_name == municipality_name)
    q = q.order_by(ZoningSource.confidence_score.desc().nulls_last())
    return list((await db.execute(q)).scalars().all())


async def _county_uses_per_town_sources(
    jurisdiction_id: uuid.UUID, db: AsyncSession,
) -> bool:
    """True when this jurisdiction has any `zoning_sources.municipality_name`
    set — the NJ-style per-town discovery pattern. False when sources are
    flat (city-jurisdiction like Draper UT)."""
    row = (
        await db.execute(
            select(ZoningSource.id)
            .where(ZoningSource.jurisdiction_id == jurisdiction_id)
            .where(ZoningSource.municipality_name.is_not(None))
            .limit(1)
        )
    ).first()
    return row is not None


def _find_source(
    sources: list[ZoningSource], *, status: str, min_confidence: int = 0,
) -> ZoningSource | None:
    """First matching source from the pre-sorted list; returns None when
    nothing qualifies."""
    for s in sources:
        if s.validation_status == status and (s.confidence_score or 0) >= min_confidence:
            return s
    return None
