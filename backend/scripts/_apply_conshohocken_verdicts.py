"""Conshohocken Borough (Montgomery County PA) — self-storage Stage-4 verdicts.

Grounded in the Borough of Conshohocken Zoning Ordinance of 2001, Chapter 27 (eCode360, fetched via
curl+browser-UA 2026-07-09). asyncpg human-UPSERT (catch #29), municipality='Conshohocken Borough'
(matches parcels.city EXACTLY — mixed case; the join m.municipality=p.city is case-sensitive, so
UPPERCASE would silently zero the batch). Catch #38: Borough of CONSHOHOCKEN, Ch. 27 (DISTINCT from
West Conshohocken Borough, Ch. 113, already grounded). Idempotent.

Ordinance facts (verbatim-verified against source HTML): self-service storage / self-storage /
mini-warehouse is NAMED nowhere. Only the LI district lists a storage/warehouse use ("Warehouse,
storage, or distribution center" §27-1402.F) and carries a same-general-character permitted catch-all
(§27-1402.I). Commercial/planned/residential districts (BC/SP/R-O) name no storage/warehouse use, so
their same-general-character catch-alls (where present) do NOT reach a storage-character use.

  LI  Limited Industrial/Research (Part 14 §27-1402) -> CONDITIONAL (0.72). Permitted uses include F
     "Warehouse, storage, or distribution center" + G "Contractor's office and storage" by-right, and I
     "Any use of the same general character as the above permitted uses" (permitted same-character
     catch-all). Self-storage is not explicitly named but is the same general character as the permitted
     warehouse/storage use (F) -> admissible via §27-1402.I (grounded on the named catch-all, subject to
     the same-character determination) -> conditional. light_industrial=permitted. 87 parcels.
  BC  Borough Commercial (Part 13 §27-1302) -> PROHIBITED (0.78). Commercial/retail/office permitted uses;
     no storage/warehouse named; same-general-character catch-all reaches only commercial-character uses
     (self-storage is not same character as the listed uses) -> not permitted.
  SP-1 Specially Planned One (Part 15 §27-1502) -> PROHIBITED (0.75). Planned mixed-use; no storage/
     warehouse named; catch-all does not reach a storage-character use -> not permitted.
  SP-3 Specially Planned Three (Part 16 §27-1602) -> PROHIBITED (0.75). Same basis; no storage named.
  SP-4 Specially Planned Four (Part 22 §27-2202) -> PROHIBITED (0.75). Same basis; no storage named.
  R-O Residential Office (Part 12 §27-1202) -> PROHIBITED (0.80). Residential/office; no storage/warehouse
     named, no same-character catch-all -> not permitted.

Armed pool = LI (87 parcels, conditional). Commercial/planned/residential-office prohibited. Residential
(BR-1/BR-2) self-evidently prohibited, not verdicted. SP-2 absent from parcels (only SP-1/SP-3/SP-4).

Run: python scripts/_apply_conshohocken_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "a59d956d-5f67-4c39-aef1-36140bd57c6f"  # Montgomery County, PA
MUNI = "Conshohocken Borough"

VERDICTS = {
    "LI": ("conditional", "permitted", 0.72, "Limited Industrial/Research District",
           "§27-1402 permitted uses: F 'Warehouse, storage, or distribution center' + G 'Contractor's office and storage' by-right, and I 'Any use of the same general character as the above permitted uses'; self-storage unnamed but same general character as the permitted warehouse/storage use (F) -> admissible via §27-1402.I -> conditional (named same-character catch-all, discretionary determination)"),
    "BC": ("prohibited", "unclear", 0.78, "Borough Commercial District",
           "§27-1302 commercial/retail/office permitted uses; no storage/warehouse named; same-general-character catch-all reaches only commercial-character uses -> self-storage not permitted"),
    "SP-1": ("prohibited", "unclear", 0.75, "Specially Planned District One",
             "§27-1502 planned mixed-use permitted list; no storage/warehouse named; same-general-character catch-all does not reach a storage-character use -> not permitted"),
    "SP-3": ("prohibited", "unclear", 0.75, "Specially Planned District Three",
             "§27-1602 planned use list; no storage/warehouse named; same-general-character catch-all does not reach a storage-character use -> not permitted"),
    "SP-4": ("prohibited", "unclear", 0.75, "Specially Planned District Four",
             "§27-2202 planned use list; no storage/warehouse named; same-general-character catch-all does not reach a storage-character use -> not permitted"),
    "R-O": ("prohibited", "unclear", 0.80, "Residential Office District",
            "§27-1202 residential/office permitted uses; no storage/warehouse named, no same-character catch-all -> not permitted"),
}

SQL = """
INSERT INTO zone_use_matrix
 (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
  light_industrial, luxury_garage_condo, citations, cited_subsection, confidence,
  human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$8,$4::use_permission_enum,$4::use_permission_enum,
  $5::use_permission_enum,'unclear',$6::jsonb,$7,$9,true,'human',$10,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET self_storage=EXCLUDED.self_storage, mini_warehouse=EXCLUDED.mini_warehouse,
  light_industrial=EXCLUDED.light_industrial, citations=EXCLUDED.citations,
  cited_subsection=EXCLUDED.cited_subsection, confidence=EXCLUDED.confidence,
  human_reviewed=true, classification_source='human', notes=EXCLUDED.notes, updated_at=now()
"""


async def main():
    url = settings.database_url.replace(":6543/", ":5432/").replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=60, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout='90s'")
        for zc, (ss, li, conf, zname, cite) in VERDICTS.items():
            cites = json.dumps([{"ordinance": "Borough of Conshohocken Zoning Ordinance of 2001, Ch. 27",
                                 "section": cite.split(";")[0].strip(),
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Conshohocken {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, light_industrial::text li, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL ORDER BY self_storage, zone_code", JID, MUNI)
        print(f"applied {len(rows)} Conshohocken Borough rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} self_storage={r['ss']:11} light_ind={r['li']:10} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
