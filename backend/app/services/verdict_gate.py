"""
Lead-eligibility gate for served zoning verdicts (audit "D2" / catch #49).

A parcel's self-storage verdict comes from a ``zone_use_matrix`` row that is
either GROUNDED (a human review, or an ordinance-grounded LLM/factory parse) or
HEURISTIC (a rule/bootstrap/crosswalk stub — e.g. the confidence-0.35
NULL-municipality county bootstrap that means "commercial ⇒ maybe" for a whole
county). Heuristic verdicts were served identically to grounded ones, so a
guess could appear as an actionable lead.

This module is the SINGLE source of truth for the demotion decision, in two
forms kept in lock-step:
  - ``gate_verdict(...)`` — the Python reference (used in tests + any per-row
    Python path),
  - ``lead_eligible_sql`` / ``gate_reason_sql`` — the equivalent SQL CASE
    expressions for the bulk LATERAL queries.

INVARIANT (do not weaken): a ``human_reviewed`` verdict — or one whose source is
grounded — is NEVER gated. That is what protects the human-reviewed armed pool.
Demotion is DEMOTE-not-delete: gated parcels still return, with
``lead_eligible=false`` + a ``gate_reason``, so the map/table can dim them and
they can be promoted later when the municipality gets a grounded verdict.
"""
from __future__ import annotations

# Grounded classification sources — an ordinance/human basis. Never gated.
GROUNDED_SOURCES: frozenset[str] = frozenset(
    {"human", "llm", "llm_rule", "op5_factory"}
)

# Below this confidence a heuristic verdict is not trustworthy enough to lead.
LEAD_CONFIDENCE_FLOOR = 0.5

# gate_reason values (also the enum of reasons the UI can render/dim by).
REASON_HEURISTIC = "heuristic_source"
REASON_LOW_CONFIDENCE = "low_confidence"
REASON_UNCLEAR = "unclear_verdict"


def is_grounded(classification_source: str | None, human_reviewed: bool) -> bool:
    """A verdict is grounded (never gated) if a human reviewed it or its source
    is an ordinance/human basis."""
    return bool(human_reviewed) or (classification_source in GROUNDED_SOURCES)


def gate_verdict(
    *,
    self_storage: str | None,
    classification_source: str | None,
    confidence: float | None,
    human_reviewed: bool,
) -> tuple[bool, str | None]:
    """Return ``(lead_eligible, gate_reason)`` for one served verdict.

    Grounded verdicts → ``(True, None)`` unconditionally (the armed-pool
    invariant). Heuristic verdicts are always demoted, with the most specific
    reason: an ``unclear`` verdict, then sub-floor/absent confidence, else the
    generic heuristic-source demotion.
    """
    if is_grounded(classification_source, human_reviewed):
        return True, None
    if (self_storage or "").lower() == "unclear":
        return False, REASON_UNCLEAR
    if confidence is None or float(confidence) < LEAD_CONFIDENCE_FLOOR:
        return False, REASON_LOW_CONFIDENCE
    return False, REASON_HEURISTIC


def _sources_sql() -> str:
    return "(" + ", ".join(f"'{s}'" for s in sorted(GROUNDED_SOURCES)) + ")"


def _grounded_sql(alias: str) -> str:
    """SQL boolean: this verdict row is grounded (never gated)."""
    return (
        f"({alias}.human_reviewed "
        f"OR {alias}.classification_source::text IN {_sources_sql()})"
    )


def lead_eligible_sql(alias: str = "zum") -> str:
    """SQL boolean expression mirroring gate_verdict()'s lead_eligible.

    A row with NO matched verdict (all columns NULL via LEFT JOIN) is NOT
    grounded → lead_eligible = false, which is the correct conservative default
    (an unscored parcel is not an actionable lead)."""
    return _grounded_sql(alias)


def gate_reason_sql(alias: str = "zum") -> str:
    """SQL text expression mirroring gate_verdict()'s gate_reason (NULL when
    the verdict is grounded / lead-eligible)."""
    return (
        f"CASE "
        f"WHEN {_grounded_sql(alias)} THEN NULL "
        f"WHEN lower({alias}.self_storage::text) = 'unclear' THEN '{REASON_UNCLEAR}' "
        f"WHEN {alias}.confidence IS NULL OR {alias}.confidence < {LEAD_CONFIDENCE_FLOOR} "
        f"THEN '{REASON_LOW_CONFIDENCE}' "
        f"ELSE '{REASON_HEURISTIC}' END"
    )
