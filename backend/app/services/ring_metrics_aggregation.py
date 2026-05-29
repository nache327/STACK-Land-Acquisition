"""Drive-time ring demographic aggregation — Python port of the canonical
frontend logic.

Mirrors `computeRingMetrics` in
[frontend/lib/isochrone-precompute.ts](../../../frontend/lib/isochrone-precompute.ts)
byte-for-byte. Server-side precompute and client-side fallback compute against
the same census-tract inputs MUST produce identical numbers, otherwise a parcel
that was scored server-side will flip its match/borderline/fail verdict the
moment a user (re-)computes on the client.

If you change anything here, change the JS function too — and bump the
`parcellogic_precompute_v*` storage key in
[isochrone-precompute.ts](../../../frontend/lib/isochrone-precompute.ts#L78)
so v8 invalidates the now-divergent client blobs.

The historical bug fixes encoded in this math (kept verbatim from JS comments):

- v2: household-weighted-mean denominator is `sum(household_count)`, NOT
  `totalPopulation`. Dividing by population deflated NJ values ~2.7× (avg
  household size), e.g. Marlboro's $148K HHI showed ~$54K.
- v5: HNW count uses ACS B19001_017E (actual ≥$200K HH count) per tract,
  not a tract-median binary proxy that over-counted tracts above the cutoff.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TractData:
    """One census tract's relevant ACS-pulled values, scoped to the part of
    the tract that intersects the drive-time isochrone. Mirrors `TractData`
    in [isochrone.ts](../../../frontend/lib/isochrone.ts) — same fields,
    same nullability semantics."""

    household_count: int | None
    population: int | None = None
    median_hhi: float | None = None
    median_home_value: float | None = None
    households_over_200k: int | None = None


@dataclass(frozen=True)
class RingMetrics:
    """Aggregated ring metrics. Matches `PrecomputedRingMetrics` in the JS
    minus the `homesOver*` lazy-fetch fields (kept NULL server-side; the
    /api/parcels/value-density endpoint owns those) and minus the
    `lastComputed` ISO string (set by the caller writing to DB)."""

    total_population: int
    hnw_households: int
    weighted_median_hhi: float
    weighted_median_home_value: float
    tract_count: int


def compute_ring_metrics(tracts: list[TractData]) -> RingMetrics:
    """Aggregate per-tract ACS values into one ring's metrics.

    Implements:
        valid = [t for t in tracts if t.household_count and t.household_count > 0]
        total_population        = sum(t.population or t.household_count or 0)
        hnw_households          = sum(t.households_over_200k or 0)
        weighted_median_hhi     = Σ(median_hhi * household_count) / Σ(household_count)
                                  over tracts where median_hhi is not null
        weighted_median_home_value = same shape, over tracts where median_home_value is not null
        tract_count = len(tracts)  # all tracts, not just valid

    Empty / zero-household ring → all numeric fields 0, tract_count = len(tracts).
    """
    valid = [t for t in tracts if t.household_count is not None and t.household_count > 0]

    total_population = sum(
        (t.population if t.population is not None else (t.household_count or 0))
        for t in valid
    )

    hnw_households = sum((t.households_over_200k or 0) for t in valid)

    hhi_tracts = [t for t in valid if t.median_hhi is not None]
    total_hhi_households = sum((t.household_count or 0) for t in hhi_tracts)
    weighted_median_hhi = (
        sum(t.median_hhi * (t.household_count or 0) for t in hhi_tracts) / total_hhi_households  # type: ignore[operator]
        if total_hhi_households > 0
        else 0.0
    )

    hv_tracts = [t for t in valid if t.median_home_value is not None]
    total_hv_households = sum((t.household_count or 0) for t in hv_tracts)
    weighted_median_home_value = (
        sum(t.median_home_value * (t.household_count or 0) for t in hv_tracts) / total_hv_households  # type: ignore[operator]
        if total_hv_households > 0
        else 0.0
    )

    return RingMetrics(
        total_population=int(total_population),
        hnw_households=int(hnw_households),
        weighted_median_hhi=float(weighted_median_hhi),
        weighted_median_home_value=float(weighted_median_home_value),
        tract_count=len(tracts),
    )
