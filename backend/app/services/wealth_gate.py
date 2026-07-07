"""
Wealth gate for needle/armed-pool queries — with the NEAR-RING OVERRIDE RULE.

The standard gate requires, at the dt=10 drive-time ring:
    median_home_value >= HV_FLOOR (475k)  AND  median_hhi >= HHI_FLOOR (100k)

NEAR-RING OVERRIDE RULE (codified 2026-07-07 — the Concord Township call;
second boundary call of this shape after the acres-floor precedent, so it is
a RULE, not a one-off waiver): a parcel failing HV at dt=10 stays live iff
  (a) HV passes at BOTH dt=2 and dt=5 (the near rings — a storage customer
      base is the near-ring wealth, not the 10-minute dilution), AND
  (b) HHI passes at ALL drive-times, AND
  (c) the dt=10 HV miss is <= NEAR_RING_MISS_TOLERANCE (5%).

Qualifying parcels are tagged 'near_ring_override' (vs 'standard') so needle
queries can distinguish them and the rule's hit-rate can be audited later.

Lock-stepped Python reference (gate_wealth) + SQL form (wealth_tag_sql) —
same pattern as verdict_gate.py. The SQL form is written against
parcel_ring_metrics with one row per (parcel_id, drive_time_minutes).
"""
from __future__ import annotations

HV_FLOOR = 475_000
HHI_FLOOR = 100_000
NEAR_RING_MISS_TOLERANCE = 0.05  # dt=10 HV may miss by at most 5%

TAG_STANDARD = "standard"
TAG_NEAR_RING = "near_ring_override"

# Drive-times consulted by the rule. dt=15 participates only in the
# HHI-everywhere condition (b).
_RULE_DTS = (2, 5, 10, 15)


def gate_wealth(rings: dict[int, tuple[float | None, float | None]]) -> str | None:
    """Return 'standard' | 'near_ring_override' | None (rejected).

    ``rings`` maps drive_time_minutes -> (median_home_value, median_hhi).
    Missing rings / NULL metrics count as failing that ring's check.
    """
    def hv(dt: int) -> float:
        return float(rings.get(dt, (None, None))[0] or 0)

    def hhi(dt: int) -> float:
        return float(rings.get(dt, (None, None))[1] or 0)

    # Standard gate: dt=10 passes both floors.
    if hv(10) >= HV_FLOOR and hhi(10) >= HHI_FLOOR:
        return TAG_STANDARD

    # Near-ring override.
    if (
        hv(2) >= HV_FLOOR
        and hv(5) >= HV_FLOOR                                  # (a)
        and all(hhi(dt) >= HHI_FLOOR for dt in _RULE_DTS if dt in rings)  # (b)
        and all(dt in rings for dt in _RULE_DTS)               # (b) needs all rings present
        and hv(10) >= HV_FLOOR * (1 - NEAR_RING_MISS_TOLERANCE)  # (c)
    ):
        return TAG_NEAR_RING
    return None


def wealth_tag_sql(parcel_alias: str = "p") -> str:
    """SQL expression evaluating to 'standard' / 'near_ring_override' / NULL
    for the parcel row aliased ``parcel_alias``. Mirrors gate_wealth().

    Aggregates parcel_ring_metrics once via a correlated subquery, so it can
    drop into any needle/armed-pool SELECT as an extra column or into a WHERE
    as ``(<expr>) IS NOT NULL``.
    """
    p = parcel_alias
    return f"""(
    SELECT CASE
        WHEN MAX(CASE WHEN r.drive_time_minutes = 10 THEN r.median_home_value END) >= {HV_FLOOR}
         AND MAX(CASE WHEN r.drive_time_minutes = 10 THEN r.median_hhi END) >= {HHI_FLOOR}
        THEN '{TAG_STANDARD}'
        WHEN MAX(CASE WHEN r.drive_time_minutes = 2  THEN r.median_home_value END) >= {HV_FLOOR}
         AND MAX(CASE WHEN r.drive_time_minutes = 5  THEN r.median_home_value END) >= {HV_FLOOR}
         AND MIN(CASE WHEN r.drive_time_minutes IN (2,5,10,15)
                      THEN COALESCE(r.median_hhi, 0) END) >= {HHI_FLOOR}
         AND COUNT(DISTINCT r.drive_time_minutes) FILTER (WHERE r.drive_time_minutes IN (2,5,10,15)) = 4
         AND MAX(CASE WHEN r.drive_time_minutes = 10 THEN r.median_home_value END)
             >= {HV_FLOOR} * {1 - NEAR_RING_MISS_TOLERANCE}
        THEN '{TAG_NEAR_RING}'
        ELSE NULL
    END
    FROM parcel_ring_metrics r
    WHERE r.parcel_id = {p}.id
)"""
