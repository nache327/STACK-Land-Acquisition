# zone_use_matrix write contract — Op-5 factory ↔ hand-path coordination

**Status:** Adam-ack'd coordination rule (2026-06-08). Implemented by
`app/services/zone_matrix_write.py`.

## The rule
**Human verdicts are truth. The Op-5 factory never overwrites a
`zone_use_matrix` row where `human_reviewed = true`.**

This mirrors Adam's existing **F2 protect-list contract**
(`op5_lib/ingestion_helpers.py::assert_no_proof_state_collision` +
`ingest_polygons_additive`), which guards **`zoning_districts`** + the Op-5
*proof* towns (Fort Lee / Garfield / Hackensack). This contract extends the same
posture **one table over** — onto `zone_use_matrix` + hand-grounded verdict rows.

## Why it's needed
The hand-path has grounded **24 munis inside the 5 factory counties** as
`human_reviewed=true` via ordinance-text citation rigor (Bergen 13, Monmouth 10,
Burlington 1) — ~1,000 "needle" parcels (Franklin Lakes I-1/I-2, Tenafly M-1,
Closter Dist-5, Cresskill P&L, Spring Lake GC, Red Bank I/LI, …). The factory
writes the same table. Without this rule a factory pass over those counties could
clobber load-bearing hand verdicts. See `scripts/_drafts/_op5_overlap_map.md`.

## Contract — `factory_safe_write(conn, jurisdiction_id, municipality, rows)`
1. **Skip human rows.** Query `human_reviewed=true` zone_codes for (jid, muni);
   filter incoming rows to exclude them (format-insensitive: `B 1` shields `B-1`).
2. **Fill-only INSERT.** Survivors `INSERT ... ON CONFLICT DO NOTHING`.
   - **The conflict target MUST name the partial-index inference:**
     `ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality, '')) WHERE deleted_at IS NULL DO NOTHING`.
     `uq_zone_matrix` is a **partial expression unique index** (migration 0029),
     not a table constraint — a bare `ON CONFLICT DO NOTHING` does NOT match it
     and raises. (This is the latent-ON-CONFLICT footgun.)
   - **Never `DO UPDATE` / UPSERT.** Belt-and-suspenders behind rule 1.
3. **Provenance.** Factory rows carry `classification_source='op5_factory_catchall'`
   (catchall stub) or `'op5_factory'` (grounded per-county). Both added to
   `classification_source_enum` in migration 0041 — previously neither existed, so
   a factory matrix write would have failed the enum. Hand rows stay `'human'`;
   the audit always distinguishes them.
4. **Returns** `{written, skipped_human, skipped_conflict}` for the audit log.

## Post-muni audit gate — `audit_muni_gap(conn, jurisdiction_id, municipality)`
After each muni, run the **matrix_codes ⊇ parcel_codes** completeness check (the
gate that caught Bedminster + 10 incompletely-grounded hand towns). Returns
`{parcel_codes, matrix_codes, gap_codes, gap_parcels}`; logs a WARNING on any gap.
**Non-blocking** — surfaces for review, does not abort the run. Mirrors
`scripts/_coverage_audit.py`.

## Scope
Only the 24 COLLISION munis are affected (fill-only mode). The other ~186 factory
munis full-run normally (no human rows → nothing to skip).

## Tests
`tests/test_factory_safe_write.py` — zero-hand-rows, 5-hand-rows-skipped,
conflict-counted, format-insensitive skip, source-cannot-masquerade-as-human,
audit-gap-flags-uncovered.
