# Session B exceptions

## Hudson County NJ — DONE (branch parcellogic/hudson-nj-jc-bind)
Jersey City bound 98.7% from NJTPA layer 7; ruled a confirmed near-total no-op (wealth on
Gold-Coast RDPs, industrial outside the wealth ring). Full detail on that branch's copy of this
file + memory `project_hudson_nj_outcome`. Pivoted to Union prep below.

---

# Union County NJ (jid 16dc5ad9-8211-47c6-bfad-93bf588b15e4) — Atlas-082025 bind DRY-RUN (2026-07-14)

DRY-RUN PREP ONLY — apply HELD pending (a) Essex distribution greenlight, (b) coordinator/Nache go.

**Source:** NJTPA Zoning Atlas 082025, statewide layer
`gis.njtpa.org/server/rest/services/LandUse/NJTPA_Zoning_Atlas_082025/MapServer/0`
(covers all 13 NJTPA counties incl. Hudson — a future Hudson re-scope option). Code field
`Abbreviated_District_Name`, long name `Full_District_Name`, filter `County='Union'` = 2,464 polygons.
Cloudflare-gated → curl+browser-UA (httpx/requests default-UA 403s).

**Coverage (centroid-within, EPSG:4326): 122,796 / 123,738 = 99.2%** of Union's NULL-zoning parcels
would bind. Union has 147,627 parcels; 4 towns already bound (Scotch Plains / Summit / Berkeley
Heights / New Providence ≈ 23,889). Every remaining town binds ~100% EXCEPT:
- **Winfield township 0/706** — genuinely absent from the Atlas (0 features anywhere; tiny enclave). Honest gap.
- **Rahway 8,192/8,401 (97.5%)** — 209 parcels outside Rahway's 73 Atlas polygons (rail/water). Minor.

**#38 code check (PASS):** Atlas codes match current ordinances — Westfield RS-6/8/10/12/16/24/40,
RM-6/6D, GB-1/2/3, CBD, C; Summit R-5/6/10/15/43, MF/MFT, B/NB, ORC/RO-60/PROD; Cranford
R-1..R-8, NC, ORC, D-C/D-T/D-B, C-2; Berkeley Heights OL, R-10/15/20, OR/OR-B, **LI**, DH/AH/HB.

**#38 cross-jurisdiction slivers:** 66 matches (0.05%) where a parcel's centroid falls in a
neighbor's Atlas polygon (e.g. 16 Westfield↔Mountainside border). Geographically correct; harmless —
the needle join keys on `parcels.city`, so a sliver carrying a neighbor's zone can't false-match that
neighbor's matrix. Leave as-is (unlike the Hudson JC-only clean; Union is whole-county in scope).

**Bug caught + fixed during prep:** ArcGIS `resultOffset` paging WITHOUT `orderByFields` is unstable
— page boundaries shift between requests, silently skipping/duplicating features (a re-download
dropped Winfield + part of Rahway, non-deterministically). Fixed with `orderByFields=OBJECTID`;
verified the paged download now retrieves all 2,464 unique OBJECTIDs and coverage is stable across runs.

**Apply artifact (ready, held):** `backend/scripts/bind_nj_atlas082025.py` — dry-run by default;
`--apply` writes `zoning_code` + `zoning_code_source='njtpa_atlas_082025'` write-once (only NULL rows,
= replace=false). Fire on greenlight:
`python scripts/bind_nj_atlas082025.py --jid 16dc5ad9-8211-47c6-bfad-93bf588b15e4 --county Union --apply`
