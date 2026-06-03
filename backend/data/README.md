# backend/data — Static reference data for the Op-5 factory pipeline

This directory holds the curated reference inputs used by the per-muni zoning
discovery, ingestion, and adjudication pipeline. Files in this directory are
authoritative inputs — they should be hand-curated or regenerated from
authoritative sources (NJDCA, county clerks, vendor directories), not produced
as pipeline outputs.

## Per-county zoning directories

Each county has a single JSON file. Records describe the three URLs the Phase 0
discovery probe needs to know about for each municipality:

- `muni_code` (string, 4-digit) — NJ DCA municipal code (`<county><muni>`)
- `muni_name` (string) — DCA muni name (includes type, e.g. "Belleville Township")
- `in_statewide_aggregator` (bool) — `true` only if the muni is covered by a
  statewide GIS aggregator. For NJ this is currently `false` for every muni
  because there is no usable statewide NJ zoning aggregator (per memory
  `ref_nj_statewide_sources.md`).
- `map_url` (string or null) — direct link to a zoning-map PDF/JPG/GIS endpoint.
  May be `null`; Phase 0 routes nulls to the operator queue.
- `ordinance_url` (string or null) — landing page for the muni's codified
  ordinance (eCode360, Municode, American Legal, etc.). May be `null` for the
  small minority of munis whose code is not yet online.
- `website_url` (string or null) — the muni's primary official website. Should
  be populated for every muni.

| County | File | Munis |
|---|---|---:|
| Bergen | `bergen_zoning_directory.json` (legacy — uses `in_njsea_zoning` field) | 70 |
| Burlington | `burlington_zoning_directory.json` | 40 |
| Essex | `essex_zoning_directory.json` | 22 |
| Middlesex | `middlesex_nj_zoning_directory.json` | 25 |
| Monmouth | `monmouth_zoning_directory.json` | 53 |

### Field-name note (Bergen vs others)

The legacy Bergen file uses `in_njsea_zoning` (NJ Sports & Exposition Authority
Meadowlands zoning) because that was the only aggregator-like surface relevant
to Bergen. The new files use the more generic `in_statewide_aggregator` per the
Op-5 Master brief. Discovery code should accept either field, treating Bergen's
`in_njsea_zoning=true` as a county-local special case.

### Schema convention

- `muni_code` follows the NJ DCA convention. County codes: Burlington=03,
  Essex=07, Middlesex=12, Monmouth=13. Within a county, codes are assigned
  alphabetically by muni name.
- Bass River, Glen Ridge, Middletown (Monmouth), New Brunswick, Sayreville,
  South Brunswick, South Orange Village, and Freehold Borough are on Municode
  rather than eCode360. All other munis on eCode360 use the canonical
  `https://ecode360.com/<short-code>` landing page.

## Other files in this directory

- `nj_municipalities.json` — the authoritative NJDCA muni-name + ordinance
  vendor classification per county (schema v2 entries include vendor metadata
  used by `nj_municipal_discovery.py`).
- `zoning_source_tenants.json` — tenant configuration for the discovery scrape.
