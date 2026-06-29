"""Town of North Castle (Westchester County, NY) — self-storage verdicts.

Grounded in the Town of North Castle Code Ch. 355 Schedules of Regulations (pasted verbatim):
§ 355-22 Business Districts (Attachment 2) and § 355-23 Office & Industrial Districts (Attach. 3-4).
Both schedules carry the explicit rule: "Any use not specifically listed shall be deemed to be
prohibited."

  CB  Central Business  -> PROHIBITED. CB = CB-A uses (retail/office/restaurant/residential) +
      vehicle fueling. Storage/warehouse/industrial is NOT listed -> prohibited per the header rule.
      (Closes the 901 N Broadway false lead — an Office listing in CB.)

  IND-A Industrial A -> self_storage CONDITIONAL. #3 "Supply houses, warehouses and other commercial
      distribution plants" + #4 "Manufacturing, fabricating, finishing or assembling" are permitted
      principal uses by right (not asterisked). Warehouse-by-right + self-storage unnamed -> conditional
      (warehouse-conditional convention). light_industrial permitted (manufacturing by right).

  PLI Planned Light Industry -> self_storage CONDITIONAL. #4 "Warehouses, excluding truck storage or
      truck terminal facilities" permitted by right; #1 industrial uses by SPECIAL USE PERMIT.
      Warehouse-by-right -> self-storage conditional; light_industrial conditional (special permit).

  RELIP Research, Electronic and Light Industrial Park -> same as PLI ("Uses as in Nos. 1, 3 and 4 in
      PLI District") -> self_storage conditional, light_industrial conditional.

HELD: IND-AA — its warehouses (#4) are asterisked (special permit / Article VII) AND scoped "At the
Westchester County Airport"; not grounded as a general self-storage allowance. Revisit if a listing lands.

Muni-specific municipality='North Castle' in the Westchester County, NY jurisdiction. asyncpg human-
UPSERT (catch #29). Run: python scripts/_apply_north_castle.py
"""
import asyncio
import json

import asyncpg

JID = "3e706886-919f-4ecf-b5aa-567040e295e8"  # Westchester County, NY
MUNI = "North Castle"

# zone -> (self_storage, mini_warehouse, light_industrial, luxury_garage_condo, confidence, cite)
VERDICTS = {
    "CB": ("prohibited", "prohibited", "prohibited", "prohibited", 0.93,
           "Ch. 355-22 Sched. of Business District Regs: CB = CB-A uses (retail/office/restaurant/"
           "residential) + vehicle fueling; storage/warehouse not listed; header: any use not listed is prohibited"),
    "IND-A": ("conditional", "conditional", "permitted", "unclear", 0.85,
              "Ch. 355-23 Sched. of Office & Industrial Regs, IND-A Industrial A #3 warehouses/distribution + "
              "#4 manufacturing permitted by right; self-storage unnamed -> conditional (warehouse-by-right convention)"),
    "PLI": ("conditional", "conditional", "conditional", "unclear", 0.85,
            "Ch. 355-23, PLI Planned Light Industry #4 warehouses permitted by right; #1 industrial by special "
            "use permit; self-storage unnamed -> conditional"),
    "RELIP": ("conditional", "conditional", "conditional", "unclear", 0.85,
              "Ch. 355-23, RELIP = PLI uses #1,3,4 (incl. #4 warehouses by right); self-storage unnamed -> conditional"),
}

SQL = """
INSERT INTO zone_use_matrix
 (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
  light_industrial, luxury_garage_condo, citations, cited_subsection, confidence,
  human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$4,$5::use_permission_enum,$6::use_permission_enum,
  $7::use_permission_enum,$8::use_permission_enum,$9::jsonb,$10,$11,true,'human',$12,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET self_storage=EXCLUDED.self_storage, mini_warehouse=EXCLUDED.mini_warehouse,
  light_industrial=EXCLUDED.light_industrial, luxury_garage_condo=EXCLUDED.luxury_garage_condo,
  citations=EXCLUDED.citations, cited_subsection=EXCLUDED.cited_subsection,
  confidence=EXCLUDED.confidence, human_reviewed=true, classification_source='human',
  notes=EXCLUDED.notes, updated_at=now()
"""


async def main():
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
    try:
        jn = await con.fetchval("SELECT name FROM jurisdictions WHERE id=$1", JID)
        assert jn and "Westchester" in jn, f"jurisdiction check failed: {jn}"
        await con.execute("SET statement_timeout='60s'")
        for zc, (ss, mw, li, lgc, conf, cite) in VERDICTS.items():
            cites = json.dumps([{"ordinance": "Town of North Castle Code Ch. 355",
                                 "section": cite.split(":")[0], "basis": cite}])
            note = f"{zc}: self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"North Castle {zc}", MUNI, ss, mw, li, lgc, cites, cite[:120], conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, light_industrial::text li, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL ORDER BY zone_code",
            JID, MUNI)
        print(f"applied {len(rows)} North Castle (Westchester) row(s):")
        for r in rows:
            print(f"  {r['zone_code']:7} self_storage={r['ss']:11} light_ind={r['li']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
