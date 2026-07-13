# Exceptions — Session C (Lake County IL)

Per-session escalation file (per 2026-07-10 directive: post to `_exceptions_<session>.md`,
not the shared `_exception_queue.md`). Genuine blockers only.

## OPEN
| # | Muni | Blocker | What's needed |
|---|---|---|---|
| C2 | Vernon Hills, Lake IL | No PUBLIC zoning-polygon layer — village runs a PRIVATE AGOL org (vernonhills.maps.arcgis.com; zoning service not shared). No GIS-Consortium folder / usrsvcs proxy found. Marginal anyway: only ~12% of parcels clear the wealth gate; O-R&D "Storage facilities" = special use. | Village GIS zoning shapefile / data request, OR a shared public layer, then Municode content-API use table + rebind. Low priority (12% gate). |
| C3 | Bannockburn, Lake IL | Only public zoning-polygon layer (GHA `gis.gha-engineers.com/.../Bannockburn/Zoning/MapServer/2`, `ZONECLASS`) returns HTTP 500 on every `/query` — can't rebind. Tiny (261 ac ≥1.5); self-storage only special-use in Office District. | A working geometry pull (paginated export / retry window) or a town shapefile. Fine to skip given low yield. |

## RESOLVED
| # | Muni | Resolution | Date |
|---|---|---|---|
| C1 | Libertyville, Lake IL | UNBLOCKED via the `utility.arcgis.com/usrsvcs/servers/fb468aa6bd77480e956c31872705fbb3/.../VLV/AGOL_VLV_Project/MapServer/0` anonymous proxy (GUID from the LibertyvilleIL community-map-viewer). Rebound 8,769 (0 orphans). Grounded (Municode Ch.26, content API): I-1 self_storage CONDITIONAL (§26-7-2.3(m)(1) NAMED NAICS 53113 special use), I-3 + O-2 self_storage PROHIBITED (absent / expressly excluded). **+3 wealth-gated needles** (I-1; Libertyville only 37% wealth-gate → industrial mostly outside the wealth rings). | 2026-07-10 |
