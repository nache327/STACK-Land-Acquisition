"""Willistown Township (Chester County PA) — self-storage verdicts.

Grounded in Willistown Zoning Ch. 139 (pasted Articles X/XIII/XIV/XV).

  I  Restricted Industrial (§139-72..75) -> CONDITIONAL.
     §139-73.A(3) "Wholesaling, warehousing and distributing" permitted BY-RIGHT; self-storage /
     self-service storage NOT named. Warehouse-by-right + self-storage-unnamed -> Cresskill convention
     => conditional (needle-eligible). §139-73.A(7) similar-use catch-all reinforces. light_industrial
     permitted (§139-73.A(4) light manufacturing by-right). conf 0.88. (catch #37: recon said "permitted";
     verbatim says warehousing-by-right + storage-unnamed = CONDITIONAL — partial, not full, inversion.)

  O   Office (§139-39) -> PROHIBITED. office/bank/lab/nursing(SE)/educational; no warehouse/storage; silence.
  HB  Highway Business (§139-67) -> PROHIBITED. storage only accessory/"in conjunction" (J) or SE materials
      yards (O.6)/wholesale (O.8); NO self-storage, NO by-right principal warehouse; silence rule.
  OP  Office-Professional (§139-70) -> PROHIBITED. office/residential/educational; no storage; silence.
  RU/R-1/R-2/R-3/RA/RA-1 -> PROHIBITED (residential/rural; self-storage not permitted; silence).

HELD (no use table in paste — surfaced to Nache, NOT applied): LI (1 parcel), TCD (Town Center),
TD. Planned Highway Corridor (§139-127) is an overlay, not a base parcel code here.

Muni-specific municipality='Willistown Township' (catch #28). asyncpg human-UPSERT (catch #29 — NOT
factory_safe_write). Idempotent. Run: python scripts/_apply_willistown.py
"""
import asyncio
import json

import asyncpg

JID = "7f5293ff-13e8-4641-a420-49bccb13b407"  # Chester County, PA
MUNI = "Willistown Township"

# zone -> (self_storage, light_industrial, confidence, cite)
VERDICTS = {
    "I":   ("conditional", "permitted", 0.88,
            "§139-73.A(3) Wholesaling, warehousing & distributing permitted by-right; self-storage unnamed -> Cresskill convention conditional; §139-73.A(7) similar-use catch-all"),
    "O":   ("prohibited", "unclear", 0.90, "§139-39 O Office — office/bank/lab/nursing(SE)/educational; no warehouse/storage; silence rule"),
    "HB":  ("prohibited", "unclear", 0.85, "§139-67 HB Highway Business — storage only accessory/'in conjunction' (J) or SE materials yards (O.6)/wholesale (O.8); no self-storage, no by-right principal warehouse; silence rule"),
    "OP":  ("prohibited", "unclear", 0.90, "§139-70 O-P Office-Professional — office/residential/educational; no warehouse/storage; silence rule"),
    "RU":  ("prohibited", "unclear", 0.88, "Rural/residential district; self-storage not a permitted use; silence rule"),
    "R-1": ("prohibited", "unclear", 0.90, "R-1 Residence District; silence rule"),
    "R-2": ("prohibited", "unclear", 0.90, "R-2 Residence District; silence rule"),
    "R-3": ("prohibited", "unclear", 0.90, "R-3 Residence District; silence rule"),
    "RA":  ("prohibited", "unclear", 0.88, "Residential-Agricultural district; silence rule"),
    "RA-1":("prohibited", "unclear", 0.88, "Residential-Agricultural district; silence rule"),
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
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout='60s'")
        for zc, (ss, li, conf, cite) in VERDICTS.items():
            cites = json.dumps([{"ordinance": "Willistown Township Zoning Ch. 139",
                                 "section": cite.split("—")[0].strip(), "basis": f"self_storage={ss} in {zc} per {cite}"}])
            note = f"{zc}: self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Willistown {zc}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr FROM zone_use_matrix "
            "WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL ORDER BY self_storage, zone_code",
            JID, MUNI)
        print(f"applied {len(rows)} Willistown Township rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} self_storage={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
