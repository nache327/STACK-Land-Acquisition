"""
Tests for the wealth gate + NEAR-RING OVERRIDE RULE (codified 2026-07-07).

The Concord / Darby / Tinicum / Aston cases are pinned to the ACTUAL prod
ring values from the Delaware County PA armed-pool readout that motivated the
rule — both Concord parcels must pass via 'near_ring_override', the other
three must still reject.
"""
from __future__ import annotations

import pytest

from app.services.wealth_gate import (
    HV_FLOOR,
    HHI_FLOOR,
    NEAR_RING_MISS_TOLERANCE,
    TAG_NEAR_RING,
    TAG_STANDARD,
    gate_wealth,
    wealth_tag_sql,
)

# rings: dt -> (median_home_value, median_hhi) — real prod values 2026-07-07
CONCORD = {2: (535_800, 129_621), 5: (495_033, 116_116),
           10: (464_411, 125_122), 15: (464_280, 128_575)}
DARBY = {2: (138_837, 59_417), 5: (155_904, 60_347),
         10: (155_982, 58_455), 15: (186_033, 64_618)}
TINICUM = {2: (171_300, 49_406), 5: (212_238, 74_276),
           10: (215_347, 75_984), 15: (214_395, 73_295)}
ASTON = {2: (322_631, 104_472), 5: (284_961, 96_489),
         10: (257_938, 88_023), 15: (325_824, 99_695)}


def test_concord_passes_via_near_ring_override():
    """dt=10 HV misses by 2.2% but dt=2/5 pass and HHI passes everywhere."""
    assert gate_wealth(CONCORD) == TAG_NEAR_RING


@pytest.mark.parametrize("rings", [DARBY, TINICUM, ASTON], ids=["darby", "tinicum", "aston"])
def test_low_wealth_corridor_still_rejects(rings):
    assert gate_wealth(rings) is None


def test_standard_pass_tagged_standard():
    rings = {2: (600_000, 130_000), 5: (550_000, 120_000),
             10: (500_000, 110_000), 15: (480_000, 105_000)}
    assert gate_wealth(rings) == TAG_STANDARD


def test_condition_a_requires_both_near_rings():
    # dt=2 passes but dt=5 misses → reject
    rings = dict(CONCORD)
    rings[5] = (474_000, 116_116)
    assert gate_wealth(rings) is None


def test_condition_b_requires_hhi_everywhere():
    # one drive-time's HHI below floor → reject
    rings = dict(CONCORD)
    rings[15] = (464_280, 99_999)
    assert gate_wealth(rings) is None


def test_condition_c_five_percent_boundary():
    # exactly at the 5% tolerance passes; just beyond fails
    at_edge = dict(CONCORD)
    at_edge[10] = (HV_FLOOR * (1 - NEAR_RING_MISS_TOLERANCE), 125_122)
    assert gate_wealth(at_edge) == TAG_NEAR_RING
    beyond = dict(CONCORD)
    beyond[10] = (HV_FLOOR * (1 - NEAR_RING_MISS_TOLERANCE) - 1, 125_122)
    assert gate_wealth(beyond) is None


def test_missing_ring_rejects_override():
    # rule requires all four rings present to evaluate condition (b)
    rings = {k: v for k, v in CONCORD.items() if k != 15}
    assert gate_wealth(rings) is None


def test_null_metrics_reject():
    rings = dict(CONCORD)
    rings[5] = (None, 116_116)
    assert gate_wealth(rings) is None


def test_sql_form_references_all_inputs():
    sql = wealth_tag_sql("p")
    for frag in (str(HV_FLOOR), str(HHI_FLOOR), TAG_STANDARD, TAG_NEAR_RING,
                 "p.id", "drive_time_minutes = 10", "drive_time_minutes = 2",
                 "drive_time_minutes = 5", "COALESCE(r.median_hhi, 0)"):
        assert frag in sql, frag
