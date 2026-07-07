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


# ── Verdict basis (human-facing provenance tag, 2026-07-07 directive) ─────────
# Rendered next to every served score/digest row so a 96-scoring heuristic
# guess can never read like a verified verdict. Values:
BASIS_HUMAN = "human-verified"        # human_reviewed / source='human'
BASIS_ORDINANCE = "ordinance-parsed"  # grounded llm / llm_rule / op5_factory
BASIS_HEURISTIC = "heuristic"         # a matrix row exists but isn't grounded
BASIS_UNGROUNDED = "ungrounded muni"  # no matrix row matched at all


def verdict_basis(
    classification_source: str | None,
    human_reviewed: bool,
    matched: bool = True,
) -> str:
    """Python reference for the basis tag. ``matched=False`` = the serving
    LATERAL found no matrix row for this parcel's (zone, municipality)."""
    if not matched:
        return BASIS_UNGROUNDED
    if human_reviewed or classification_source == "human":
        return BASIS_HUMAN
    if classification_source in GROUNDED_SOURCES:
        return BASIS_ORDINANCE
    return BASIS_HEURISTIC


def verdict_basis_sql(alias: str = "zum") -> str:
    """SQL mirror of verdict_basis(). A LEFT-JOINed miss (source IS NULL and
    human_reviewed IS NULL) yields 'ungrounded muni'."""
    return (
        f"CASE "
        f"WHEN {alias}.classification_source IS NULL AND {alias}.human_reviewed IS NULL "
        f"THEN '{BASIS_UNGROUNDED}' "
        f"WHEN COALESCE({alias}.human_reviewed, false) "
        f"  OR {alias}.classification_source::text = 'human' THEN '{BASIS_HUMAN}' "
        f"WHEN {alias}.classification_source::text IN {_sources_sql()} "
        f"THEN '{BASIS_ORDINANCE}' "
        f"ELSE '{BASIS_HEURISTIC}' END"
    )
