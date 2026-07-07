"""
Unit tests for the lead-eligibility gate (catch #49).

The load-bearing test is test_armed_pool_invariant_*: a human_reviewed (or
otherwise grounded) verdict is NEVER demoted, regardless of confidence or the
self_storage value — this is what guarantees the cross-corridor armed pool
cannot change lead status.
"""
from __future__ import annotations

import pytest

from app.services.verdict_gate import (
    GROUNDED_SOURCES,
    REASON_HEURISTIC,
    REASON_LOW_CONFIDENCE,
    REASON_UNCLEAR,
    gate_verdict,
    lead_eligible_sql,
    gate_reason_sql,
)


# ── INVARIANT: grounded verdicts are never gated ─────────────────────────────

@pytest.mark.parametrize("source", sorted(GROUNDED_SOURCES))
@pytest.mark.parametrize("verdict", ["permitted", "conditional", "prohibited", "unclear"])
@pytest.mark.parametrize("conf", [None, 0.0, 0.35, 0.5, 0.99])
def test_grounded_source_never_gated(source, verdict, conf):
    eligible, reason = gate_verdict(
        self_storage=verdict, classification_source=source,
        confidence=conf, human_reviewed=False,
    )
    assert eligible is True and reason is None


@pytest.mark.parametrize("source", ["rule", "unclear", "crosswalk", "inherited_pending", None])
@pytest.mark.parametrize("verdict", ["permitted", "conditional", "unclear"])
@pytest.mark.parametrize("conf", [None, 0.35, 0.99])
def test_human_reviewed_never_gated(source, verdict, conf):
    """Even a low-confidence, rule-sourced row is lead-eligible if a human
    reviewed it — the armed-pool invariant."""
    eligible, reason = gate_verdict(
        self_storage=verdict, classification_source=source,
        confidence=conf, human_reviewed=True,
    )
    assert eligible is True and reason is None


# ── heuristic verdicts are demoted with the right reason ─────────────────────

def test_heuristic_unclear_is_unclear_reason():
    eligible, reason = gate_verdict(
        self_storage="unclear", classification_source="unclear",
        confidence=0.35, human_reviewed=False,
    )
    assert eligible is False and reason == REASON_UNCLEAR


def test_heuristic_low_confidence():
    # the confidence-0.35 county bootstrap signature
    eligible, reason = gate_verdict(
        self_storage="conditional", classification_source="rule",
        confidence=0.35, human_reviewed=False,
    )
    assert eligible is False and reason == REASON_LOW_CONFIDENCE


def test_heuristic_decent_confidence_still_demoted():
    eligible, reason = gate_verdict(
        self_storage="permitted", classification_source="crosswalk",
        confidence=0.8, human_reviewed=False,
    )
    assert eligible is False and reason == REASON_HEURISTIC


def test_confidence_floor_boundary():
    # exactly at the floor is eligible-side of the heuristic reason split
    _, reason_at = gate_verdict(
        self_storage="conditional", classification_source="rule",
        confidence=0.5, human_reviewed=False,
    )
    assert reason_at == REASON_HEURISTIC  # >= floor → not low_confidence
    _, reason_below = gate_verdict(
        self_storage="conditional", classification_source="rule",
        confidence=0.499, human_reviewed=False,
    )
    assert reason_below == REASON_LOW_CONFIDENCE


# ── SQL fragments stay in step with the Python reference ─────────────────────

def test_sql_fragments_reference_all_inputs():
    le = lead_eligible_sql("zum")
    gr = gate_reason_sql("zum")
    for frag in (le, gr):
        assert "zum.human_reviewed" in frag
        assert "zum.classification_source" in frag
    assert "zum.self_storage" in gr and "zum.confidence" in gr
    # grounded sources all present in the SQL IN-list
    for s in GROUNDED_SOURCES:
        assert f"'{s}'" in le
    # all three reasons present
    for r in (REASON_UNCLEAR, REASON_LOW_CONFIDENCE, REASON_HEURISTIC):
        assert f"'{r}'" in gr


# ── verdict basis (2.2 enforcement, 2026-07-07) ──────────────────────────────

from app.services.verdict_gate import (  # noqa: E402
    BASIS_HEURISTIC,
    BASIS_HUMAN,
    BASIS_ORDINANCE,
    BASIS_UNGROUNDED,
    verdict_basis,
    verdict_basis_sql,
)


def test_basis_human_wins():
    assert verdict_basis("rule", True) == BASIS_HUMAN
    assert verdict_basis("human", False) == BASIS_HUMAN


def test_basis_ordinance_for_grounded_sources():
    for s in ("llm", "llm_rule", "op5_factory"):
        assert verdict_basis(s, False) == BASIS_ORDINANCE


def test_basis_heuristic_and_ungrounded():
    assert verdict_basis("unclear", False) == BASIS_HEURISTIC
    assert verdict_basis("crosswalk", False) == BASIS_HEURISTIC
    assert verdict_basis(None, False, matched=False) == BASIS_UNGROUNDED


def test_basis_sql_covers_all_tags():
    sql = verdict_basis_sql("zum")
    for tag in (BASIS_HUMAN, BASIS_ORDINANCE, BASIS_HEURISTIC, BASIS_UNGROUNDED):
        assert f"'{tag}'" in sql
    assert "zum.classification_source IS NULL AND zum.human_reviewed IS NULL" in sql
