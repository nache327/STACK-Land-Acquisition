"""
ARMED-POOL INVARIANT at the scoring layer (2.2 enforcement, approved 2026-07-07).

score_for_parcel persists lead_eligible/gate_reason/verdict_basis onto every
score row. The load-bearing invariant: a human-reviewed (or grounded-source)
verdict is NEVER demoted, whatever its confidence or verdict value — this is
what guarantees the 363+ cross-corridor armed pool cannot lose lead status
when scoring re-runs. Pure tests (no DB); the SQL side is covered by
test_heuristic_gate_db's parity test and was verified read-only against prod
(48,110 human-reviewed lead-visible parcels, 0 demoted).
"""
from __future__ import annotations

import pytest

from app.services.buybox_scoring import ParcelInputs, score_for_parcel


def _inputs(**kw) -> ParcelInputs:
    base = dict(
        parcel_id=1, storage_permission="conditional", acres=2.0, aadt=None,
        in_flood_zone=False, in_wetland=False, has_structure=False,
        verdict_matched=True,
    )
    base.update(kw)
    return ParcelInputs(**base)


@pytest.mark.parametrize("verdict", ["permitted", "conditional", "prohibited", "unclear"])
@pytest.mark.parametrize("conf", [None, 0.0, 0.35, 0.99])
def test_armed_pool_invariant_human_reviewed_never_demoted(verdict, conf):
    s = score_for_parcel(_inputs(
        storage_permission=verdict, classification_source="rule",
        confidence=conf, human_reviewed=True,
    ))
    assert s.lead_eligible is True
    assert s.gate_reason is None
    assert s.verdict_basis == "human-verified"


@pytest.mark.parametrize("source", ["llm", "llm_rule", "op5_factory"])
def test_grounded_sources_never_demoted(source):
    s = score_for_parcel(_inputs(
        classification_source=source, confidence=0.72, human_reviewed=False,
    ))
    assert s.lead_eligible is True and s.gate_reason is None
    assert s.verdict_basis == "ordinance-parsed"


def test_heuristic_demoted_not_deleted():
    """Demote-don't-delete: the score row still computes (score/tier/factors
    intact) — only the eligibility flag and reason change."""
    s = score_for_parcel(_inputs(
        classification_source="unclear", confidence=0.35, human_reviewed=False,
    ))
    assert s.lead_eligible is False
    assert s.gate_reason == "low_confidence"
    assert s.verdict_basis == "heuristic"
    assert s.score >= 0 and s.factors  # the row itself survives


def test_ungrounded_muni_ineligible():
    s = score_for_parcel(_inputs(
        storage_permission=None, classification_source=None,
        confidence=None, human_reviewed=False, verdict_matched=False,
    ))
    assert s.lead_eligible is False
    assert s.verdict_basis == "ungrounded muni"
