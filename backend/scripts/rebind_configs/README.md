# rebind_configs/ — one JSON per municipality

`backfill_zoning_from_districts.py` globs this directory (`load_configs()`) instead of
carrying a shared `CONFIGS` dict. **A new muni = a new file here** — parallel sessions never
edit a shared literal, so there are no merge conflicts on the rebind config.

## Schema
```json
{
  "muni": "NORWOOD",                 // UPPERCASE, must match parcels.city
  "jid": "NORFOLK",                  // alias {NORFOLK,MIDDLESEX} or a raw jurisdiction UUID
  "url": "MAPC",                     // "MAPC" | "NMCOG/<layer>" | raw https ArcGIS layer URL
  "code_field": "zo_code",           // ArcGIS field holding the district code
  "where": "muni='Norwood'",         // ArcGIS query filter (MAPC: muni=; NMCOG per-town layer: 1=1)
  "strip_prefix": "^\\d+",           // regex stripped from code BEFORE code_map; null for none (NMCOG)
  "code_map": {"OldGIS": "Bylaw"},   // GIS-code -> ordinance-code rename, applied after strip
  "ordinance_districts": ["..."],    // the bylaw's real district codes (gate a: layer vocab ⊆ this)
  "nonbinding": ["WA","ROW"],        // real-but-never-bound classes (water/ROW); kept in report
  "expected_count": [8, 11],         // [lo,hi] district-count sanity (gate b)
  "overlay": {                       // optional — SS-overlay tagging (Billerica pattern)
    "url": "NMCOG/2", "code_field": "Zone_Code", "tag_codes": ["SS"]
  },
  "notes": "source + provenance one-liner"
}
```

## Adding a muni (parallel-safe)
1. Recon the source layer (MAPC layer 2 for Metro-Boston 101 munis; NMCOG per-town; else town GIS).
2. Drop a `<muni>.json` here with the schema above.
3. `python scripts/backfill_zoning_from_districts.py --muni <MUNI>` (dry-run) → eyeball the diff
   artifact `_drafts/_rebind_diff_<muni>_dry.json` → `--apply` once gates a/b/d pass.
4. If MAPC gate-b fails (stale/consolidated vocab, e.g. Braintree), point `url` at the town GIS
   layer and set `code_field`/`code_map` accordingly — same file, no code change.
