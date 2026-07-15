# Session B — Burlington NJ wealth-tail (jid d316fb43-d0e6-4359-aa47-6475fa99cc0f)

## FINDING: structural sub-$475k-ring NO-OP — 0 needles, grounding not warranted (2026-07-15)

Queue item 3 asked to ground Moorestown / Medford / Mount Laurel as an unverdicted wealth-tail.
Investigation shows they CANNOT yield wealth-gated needles:

| town | parcels | bound | ring dt10 | HHI≥100k | HV≥475k | ring max HV | wealth&1.5ac |
|------|--------:|------:|----------:|---------:|--------:|------------:|-------------:|
| Moorestown township  | 7,575  | **0 (unbound)** | 7,575  | all | **0** | $356,064 | 0 |
| Medford township     | 9,880  | 9,877           | 9,880  | all | **0** | $411,931 | 0 |
| Mount Laurel township| 18,518 | **0 (unbound)** | 18,518 | all | **0** | $408,912 | 0 |

The needle gate requires dt10 `median_home_value ≥ 475000 AND median_hhi ≥ 100000`. These towns
clear HHI comfortably (avg $115k–134k) but their **10-min-drive-ring median home value never reaches
$475k** (maxes $356k / $412k / $409k). So 0 parcels pass the wealth gate → **0 needles no matter what
is grounded.** Income-affluent, but the surrounding Burlington-County catchment's home values are below
the gate (ring-vs-town distinction; same lesson as Fairfield CT Batch-2 sub-$475k targets and
`needle_vs_coverage_metric`).

**Decision (not grounded):** binding Moorestown + Mount Laurel (they're unbound) would require a
non-NJTPA source — **Burlington is DVRPC, NOT in the NJTPA Atlas** (Atlas covers only the 13 NJTPA
counties) — and grounding all three yields 0 needles regardless. Per the "correct no-op ≠ gap" steer,
not investing in a 36k-parcel bind+ground for 0 needles.

**Hand-back to coordinator:** Burlington wealth-tail = confirmed no-op at the current $475k HV gate. If
coverage-documentation is wanted anyway, Moorestown/Mount Laurel need a DVRPC/town-GIS bind first. If
the expectation was that Moorestown clears the gate, that's a ring-precompute/threshold question (the
town's own home values exceed its 10-min-ring median), not a grounding gap.
