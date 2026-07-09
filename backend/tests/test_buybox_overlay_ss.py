"""SS-overlay upgrade at the scoring layer.

A parcel inside a mapped Self-Service Storage overlay (parcels.overlay_tags
contains 'SS') has an affirmative special-permit path to self-storage even
where the base district prohibits it (Billerica § 11.6). The scorer must lift
the effective verdict to 'conditional' — and, when the base row is grounded
(human), that makes the parcel a lead. Never downgrades a permitted base.
"""
from __future__ import annotations

import pytest

from app.services.buybox_scoring import (
    ParcelInputs,
    _has_ss_overlay,
    score_for_parcel,
)


def _inputs(**kw) -> ParcelInputs:
    base = dict(
        parcel_id=1, storage_permission="prohibited", acres=5.0, aadt=None,
        in_flood_zone=False, in_wetland=False, has_structure=False,
        classification_source="human", confidence=0.95, human_reviewed=True,
        verdict_matched=True,
    )
    base.update(kw)
    return ParcelInputs(**base)


class TestHasSsOverlayParsing:
    def test_none(self):
        assert _has_ss_overlay(None) is False

    def test_empty_list(self):
        assert _has_ss_overlay([]) is False

    def test_list_with_ss(self):
        assert _has_ss_overlay(["SS"]) is True

    def test_list_without_ss(self):
        assert _has_ss_overlay(["MCROD", "TH"]) is False

    def test_json_string(self):
        assert _has_ss_overlay('["SS"]') is True

    def test_json_string_without_ss(self):
        assert _has_ss_overlay('["RC"]') is False


class TestOverlayUpgrade:
    def test_prohibited_base_upgrades_to_conditional_and_leads(self):
        # The Billerica case: I-district base ss=prohibited (human), overlay grants it.
        s = score_for_parcel(_inputs(storage_permission="prohibited", overlay_ss=True))
        storage = next(f for f in s.factors if f["label"] == "Storage")
        assert storage["reason"] == "Conditional use"
        assert any(f["label"] == "SS overlay" for f in s.factors)
        assert s.lead_eligible is True  # grounded human conditional => lead

    def test_unclear_base_upgrades(self):
        s = score_for_parcel(_inputs(storage_permission="unclear", overlay_ss=True))
        storage = next(f for f in s.factors if f["label"] == "Storage")
        assert storage["reason"] == "Conditional use"

    def test_no_overlay_stays_prohibited(self):
        s = score_for_parcel(_inputs(storage_permission="prohibited", overlay_ss=False))
        storage = next(f for f in s.factors if f["label"] == "Storage")
        assert storage["reason"] == "Prohibited by zoning"
        assert not any(f["label"] == "SS overlay" for f in s.factors)

    def test_permitted_base_not_downgraded(self):
        s = score_for_parcel(_inputs(storage_permission="permitted", overlay_ss=True))
        storage = next(f for f in s.factors if f["label"] == "Storage")
        assert storage["reason"] == "Permitted by zoning"
        # overlay flag present but no upgrade fired (base already better)
        assert not any(f["label"] == "SS overlay" for f in s.factors)

    def test_overlay_score_beats_bare_prohibited(self):
        with_ov = score_for_parcel(_inputs(storage_permission="prohibited", overlay_ss=True))
        without = score_for_parcel(_inputs(storage_permission="prohibited", overlay_ss=False))
        assert with_ov.score > without.score
