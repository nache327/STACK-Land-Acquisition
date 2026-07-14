# Session C — Passaic NJ batch-1 (parcellogic/passaic-nj-batch1)

## Passaic County NJ (jid 7a9ed95d-df89-4864-a203-f831a987b562)
Stage-1 bind (NJTPA Atlas 082025) applied: **125,694 / 125,785 = 99.9% bound**. Stage-3 ring
precompute already complete (125,785 dt=10, 25,687 wealth-pass). Batch-1 grounded the 3 in-ring
industrial/CI towns from the wealth-ring discovery-rank: **Wayne, Hawthorne, Wanaque**.

### Needle outcome
- **Wayne township — I (Industrial)**: self-storage a NAMED by-right use (§134-48.1 E "Self-storage
  facilities" + D "Warehousing") → **21 wealth-gated needles**.
- **Hawthorne borough — I-1**: "indoor warehousing and storage" by-right (§540-167A), self-storage
  not separately named → warehouse-by-right convention → conditional → **27 wealth-gated needles**.
- **Wanaque borough — IR-1**: correct no-op — §114-14A permits "wholesaling, warehousing and
  distribution activities" = a wholesale/distribution logistics use (Berkeley-Heights warehouse-vs-
  wholesale rule), NOT customer self-storage (named nowhere in Ch. 114) → prohibited.
- **Batch-1 total: 48 wealth-gated self-storage needles.**

### Escalation — Wayne MLR3D-4 (Mount Laurel Round-3 District 4), 3 in-ring parcels
Grounded **conservatively prohibited** pending confirmation. §134-54.8 lists "Self-storage
facilities" as a permitted PRINCIPAL use, but ONLY on the portion of the district encompassed by
Block 3101, Lots 12/13 (the AvalonBay affordable-housing settlement commercial parcel); the Block
3103 portion is residential. The 3 Atlas-bound MLR3D-4 parcels could not be confirmed as Block 3101,
so I did not assert self-storage there (would risk 3 false needles). If a block check confirms any of
the 3 sit on Block 3101 Lots 12/13, flip those to self_storage=conditional. Immaterial to the headline.

### Follow-up towns (in-ring industrial/CI, not yet ground)
- **Pompton Lakes** — HI (2 in-ring) + M (2) tiny industrial; C-R/B-2/CBR/DBD-2 commercial. ~worth a
  small batch-2 if a block check warrants; low yield.
- **North Haledon** — wealthy but NO industrial zone in-ring (RA-1/2/3 residential + B-1/B-2 business);
  correct no-op, not forced (Hudson lesson). Business zones don't name self-storage.
- Urban cores (Paterson/Clifton/Passaic) — industrial exists but OUTSIDE the wealth ring → correct
  no-ops, not forced.

## Process note — canonical bind script hardened
`scripts/bind_nj_atlas082025.py` per-row `UPDATE` loop (all rows in one transaction) ran 60+ min on
Passaic (125k rows) with nothing committed. Replaced with a single `UPDATE … FROM unnest($ids,$codes)`
batched write (5,000/chunk) — bit-identical result (same Atlas fetch/paging fix, centroid-within
EPSG:4326, write-once on NULL, provenance njtpa_atlas_082025), ~1-2 min for a full county. Hardens the
template for every future NJ bind (Nache-approved swap).
