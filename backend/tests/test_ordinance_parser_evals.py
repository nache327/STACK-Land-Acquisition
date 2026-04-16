"""
Ordinance parser evaluation tests.

Golden-file approach:
  - tests/fixtures/draper_ut/ordinance_excerpt.txt  — pre-fetched ordinance text
  - tests/fixtures/draper_ut/parser_snapshot.json   — recorded Claude response
  - tests/fixtures/draper_ut/expected_matrix.json   — hand-labeled ground truth

How to record a fresh snapshot (requires ANTHROPIC_API_KEY):
    RECORD_SNAPSHOT=1 pytest tests/test_ordinance_parser_evals.py::TestParserIntegration -v -m integration

Subsequent runs replay the snapshot without calling Claude:
    pytest tests/test_ordinance_parser_evals.py -v
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.services.ordinance_parser import (
    _apply_luxury_garage_inference,
    _build_output,
    _validate_parser_output,
    parse_ordinance_sections,
)
from app.schemas.zone_use_matrix import ParserOutput

# ─── Fixture paths ────────────────────────────────────────────────────────────

FIXTURES = Path(__file__).parent / "fixtures" / "draper_ut"
ORDINANCE_PATH = FIXTURES / "ordinance_excerpt.txt"
SNAPSHOT_PATH = FIXTURES / "parser_snapshot.json"
EXPECTED_PATH = FIXTURES / "expected_matrix.json"

USE_TYPES = ["self_storage", "mini_warehouse", "light_industrial", "luxury_garage_condo"]


# ─── Helpers ─────────────────────────────────────────────────────────────────

def load_expected() -> list[dict]:
    data = json.loads(EXPECTED_PATH.read_text())
    return [z for z in data["zones"] if not z.get("_comment")]


def accuracy(actual: ParserOutput, expected: list[dict]) -> float:
    """Fraction of (zone, use_type) pairs that match expected."""
    by_code = {z.code: z for z in actual.zones}
    correct = total = 0
    for exp in expected:
        code = exp["code"]
        if code not in by_code:
            total += len(USE_TYPES)
            continue
        actual_zone = by_code[code]
        for use in USE_TYPES:
            total += 1
            if getattr(actual_zone, use) == exp.get(use):
                correct += 1
    return correct / total if total > 0 else 0.0


def output_from_snapshot() -> ParserOutput:
    data = json.loads(SNAPSHOT_PATH.read_text())
    return _build_output(data["raw_response"])


# ─── Unit tests (no API, no DB) ───────────────────────────────────────────────

class TestParserUnit:
    def test_fixtures_exist(self):
        assert ORDINANCE_PATH.exists(), f"Missing fixture: {ORDINANCE_PATH}"
        assert EXPECTED_PATH.exists(), f"Missing fixture: {EXPECTED_PATH}"

    def test_expected_matrix_has_required_zones(self):
        expected = load_expected()
        codes = {z["code"] for z in expected}
        for required in ["M1", "CBP", "CG", "CS"]:
            assert required in codes, f"Required zone {required} missing from expected_matrix.json"

    def test_validate_parser_output_accepts_valid_json(self):
        sample = json.dumps({
            "zones": [{
                "code": "M1",
                "name": "Light Industrial",
                "self_storage": "permitted",
                "mini_warehouse": "permitted",
                "light_industrial": "permitted",
                "luxury_garage_condo": "permitted",
                "citations": [{"section": "9-14-020(B)", "quote": "Self-storage warehouses"}],
                "confidence": 0.97,
                "notes": None,
            }],
            "unknown_zones": [],
            "parser_warnings": [],
        })
        out = _validate_parser_output(sample)
        assert out.zones[0].code == "M1"

    def test_validate_parser_output_rejects_invalid(self):
        with pytest.raises(Exception):
            _validate_parser_output("not valid json at all {{{")

    def test_luxury_garage_inference_from_mini_warehouse(self):
        zone = {
            "code": "M1",
            "self_storage": "permitted",
            "mini_warehouse": "permitted",
            "light_industrial": "permitted",
            "luxury_garage_condo": "unclear",
        }
        result = _apply_luxury_garage_inference(zone)
        assert result["luxury_garage_condo"] == "permitted"

    def test_luxury_garage_inference_from_light_industrial_only(self):
        zone = {
            "code": "IN",
            "self_storage": "prohibited",
            "mini_warehouse": "prohibited",
            "light_industrial": "permitted",
            "luxury_garage_condo": "unclear",
        }
        result = _apply_luxury_garage_inference(zone)
        assert result["luxury_garage_condo"] == "conditional"

    def test_luxury_garage_inference_prohibited_when_nothing_permitted(self):
        zone = {
            "code": "R-1-10",
            "self_storage": "prohibited",
            "mini_warehouse": "prohibited",
            "light_industrial": "prohibited",
            "luxury_garage_condo": "unclear",
        }
        result = _apply_luxury_garage_inference(zone)
        assert result["luxury_garage_condo"] == "prohibited"

    def test_luxury_garage_inference_respects_explicit_value(self):
        zone = {
            "code": "CG",
            "self_storage": "permitted",
            "mini_warehouse": "permitted",
            "light_industrial": "prohibited",
            "luxury_garage_condo": "conditional",  # explicit — should not be overridden
        }
        result = _apply_luxury_garage_inference(zone)
        assert result["luxury_garage_condo"] == "conditional"

    def test_snapshot_replay_accuracy(self):
        """If a snapshot exists, assert >= 90% accuracy against expected matrix."""
        if not SNAPSHOT_PATH.exists():
            pytest.skip("No snapshot recorded yet. Run with RECORD_SNAPSHOT=1 -m integration.")
        output = output_from_snapshot()
        expected = load_expected()
        acc = accuracy(output, expected)
        assert acc >= 0.90, (
            f"Snapshot accuracy {acc:.0%} is below the 90% threshold. "
            "Review expected_matrix.json or re-record the snapshot."
        )

    def test_snapshot_required_zones_permit_self_storage(self):
        """Spec requirement: M1, CBP, CG, CS must permit (or conditionally permit) self-storage."""
        if not SNAPSHOT_PATH.exists():
            pytest.skip("No snapshot recorded yet.")
        output = output_from_snapshot()
        by_code = {z.code: z for z in output.zones}
        for code in ["M1", "CBP", "CG", "CS"]:
            if code in by_code:
                assert by_code[code].self_storage in ("permitted", "conditional"), (
                    f"Zone {code}: expected self_storage permitted or conditional, "
                    f"got '{by_code[code].self_storage}'"
                )


# ─── Integration tests (calls real Claude API) ────────────────────────────────

@pytest.mark.integration
class TestParserIntegration:
    @pytest.mark.asyncio
    async def test_draper_parser_accuracy(self):
        """
        Run the full parser against the Draper ordinance fixture and assert
        accuracy >= 90% against the hand-labeled expected_matrix.json.

        Set RECORD_SNAPSHOT=1 to save Claude's response as the golden snapshot.
        """
        assert ORDINANCE_PATH.exists(), f"Missing: {ORDINANCE_PATH}"
        text = ORDINANCE_PATH.read_text()
        known_codes = ["M1", "ML", "CBP", "CG", "CS", "CN", "CB", "CO", "R-1-10", "RM", "OS", "PF"]

        output = await parse_ordinance_sections(
            text,
            "Draper City, UT",
            known_codes,
            snapshot_path=SNAPSHOT_PATH,
        )

        expected = load_expected()
        acc = accuracy(output, expected)

        # Spec hard requirements
        by_code = {z.code: z for z in output.zones}
        for code in ["M1", "CBP", "CG", "CS"]:
            if code in by_code:
                assert by_code[code].self_storage in ("permitted", "conditional"), (
                    f"Spec requirement failed: Zone {code} self_storage = "
                    f"'{by_code[code].self_storage}'"
                )

        assert acc >= 0.90, (
            f"Parser accuracy {acc:.0%} < required 90%.\n"
            f"Zones parsed: {[z.code for z in output.zones]}\n"
            f"Expected zones: {[z['code'] for z in expected]}"
        )
