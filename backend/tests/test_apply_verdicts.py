"""Unit tests for the data-driven verdict applier's pure logic (no DB).

Covers schema validation and the present-zone planning that replaces the
per-muni _apply_*.py scripts.
"""
import json

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from apply_verdicts import SpecError, plan_rows, validate_spec  # noqa: E402


def _spec(**over):
    base = {
        "jurisdiction_id": "b05b7317-b412-492c-a56c-433d447d17bf",
        "municipality": "Apex",
        "ordinance": "Apex UDO Table 4.2.2",
        "cited_subsection": "UDO Table 4.2.2",
        "zones": {
            "LI": {
                "zone_name": "LI Light Industrial",
                "self_storage": "permitted", "mini_warehouse": "permitted",
                "light_industrial": "permitted", "luxury_garage_condo": "prohibited",
                "confidence": 0.88, "quote": "P in LI column",
            },
            "PC": {
                "zone_name": "PC", "self_storage": "prohibited",
                "mini_warehouse": "prohibited", "light_industrial": "prohibited",
                "luxury_garage_condo": "prohibited", "confidence": 0.85,
                "quote": "blank in Self-service storage row",
            },
        },
    }
    base.update(over)
    return base


def test_validate_ok():
    validate_spec(_spec())  # no raise


@pytest.mark.parametrize("mutate,msg", [
    (lambda s: s.pop("jurisdiction_id"), "jurisdiction_id"),
    (lambda s: s.pop("ordinance"), "ordinance"),
    (lambda s: s.update(zones={}), "zones"),
])
def test_validate_missing_fields(mutate, msg):
    s = _spec()
    mutate(s)
    with pytest.raises(SpecError) as e:
        validate_spec(s)
    assert msg in str(e.value)


def test_validate_bad_verdict_value():
    s = _spec()
    s["zones"]["LI"]["self_storage"] = "maybe"
    with pytest.raises(SpecError) as e:
        validate_spec(s)
    assert "self_storage" in str(e.value)


def test_validate_requires_quote():
    s = _spec()
    del s["zones"]["LI"]["quote"]
    with pytest.raises(SpecError):
        validate_spec(s)


def test_validate_confidence_range():
    s = _spec()
    s["zones"]["LI"]["confidence"] = 1.5
    with pytest.raises(SpecError):
        validate_spec(s)


def test_plan_filters_to_present_zones():
    s = _spec()
    rows, skipped = plan_rows(s, present_zones={"LI"})
    codes = {r["zone_code"] for r in rows}
    assert codes == {"LI"}
    assert skipped == ["PC"]


def test_plan_all_ignores_presence():
    s = _spec()
    rows, skipped = plan_rows(s, present_zones={"LI"}, apply_all=True)
    assert {r["zone_code"] for r in rows} == {"LI", "PC"}
    assert skipped == []


def test_plan_threads_municipality_and_citation():
    s = _spec()
    rows, _ = plan_rows(s, present_zones=None)
    li = next(r for r in rows if r["zone_code"] == "LI")
    assert li["municipality"] == "Apex"
    cite = json.loads(li["citations"])[0]
    assert cite["ordinance"] == "Apex UDO Table 4.2.2"
    assert cite["section"] == "UDO Table 4.2.2"     # falls back to cited_subsection
    assert cite["quote"] == "P in LI column"
    assert li["self_storage"] == "permitted" and li["luxury_garage_condo"] == "prohibited"


def test_plan_none_present_writes_all():
    # present_zones=None means "don't filter" — used for county-default specs.
    rows, skipped = plan_rows(_spec(), present_zones=None)
    assert len(rows) == 2 and skipped == []
