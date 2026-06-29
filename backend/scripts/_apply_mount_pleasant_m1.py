"""Town of Mount Pleasant (Westchester County, NY) — M-1 self-storage verdict.

Grounded in the Town of Mount Pleasant Code Ch. 218, Schedule of Regulations, Nonresidence
Districts IV (218 Attachment 16), district "M1 Planned Light Industry" (pasted verbatim):

  M1 Planned Light Industry — Permitted Principal Uses:
    "1. Any lawful, nonresidential use as provided in Article IV, and including any
        nonresidential use listed above."

Self-storage / mini-warehouse is a lawful nonresidential use → PERMITTED BY RIGHT in M-1.
Triple-confirmed in the same schedule: C-GC (a district "listed above") permits "Wholesale or
storage businesses" as a principal use; OB6 permits "Enclosed storage, warehousing and
distribution"; and the OB-MP zone explicitly lists "Warehousing and distribution uses/self-storage".
Light industry permitted by right (the district IS Planned Light Industry). Luxury-garage-condo
("car storage facility", cf. §218-61.1) is likewise a nonresidential use permitted by right in M-1.

Muni-specific municipality='Mount Pleasant' in the Westchester County, NY jurisdiction.
asyncpg human-UPSERT (catch #29). Run: python scripts/_apply_mount_pleasant_m1.py
"""
import asyncio
import json

import asyncpg

JID = "3e706886-919f-4ecf-b5aa-567040e295e8"  # Westchester County, NY
MUNI = "Mount Pleasant"
CITE = ("Town of Mount Pleasant Code Ch. 218 Schedule of Regulations, Nonresidence Districts IV "
        "(218 Attachment 16), M1 Planned Light Industry — Permitted Principal Uses §1: "
        "'Any lawful, nonresidential use ... and including any nonresidential use listed above'")
SUBSEC = "Ch. 218, Sched. of Regs., Nonresidence Districts IV, M1 Planned Light Industry, Permitted Principal Uses §1"

# zone -> (self_storage, mini_warehouse, light_industrial, luxury_garage_condo, confidence)
VERDICTS = {
    "M-1": ("permitted", "permitted", "permitted", "permitted", 0.95),
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
        for zc, (ss, mw, li, lgc, conf) in VERDICTS.items():
            cites = json.dumps([{"ordinance": "Town of Mount Pleasant Code Ch. 218",
                                 "section": "Schedule of Regulations, Nonresidence Districts IV, M1 Planned Light Industry",
                                 "basis": f"self_storage={ss} in {zc}: M1 permits any lawful nonresidential use by right; "
                                          f"storage/warehousing confirmed in C-GC, OB6, OB-MP"}])
            note = f"{zc}: self_storage {ss} by right. {CITE}"
            await con.execute(SQL, JID, zc, f"Mount Pleasant {zc} Planned Light Industry",
                              MUNI, ss, mw, li, lgc, cites, SUBSEC, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, light_industrial::text li, "
            "luxury_garage_condo::text lgc, confidence, human_reviewed hr FROM zone_use_matrix "
            "WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL ORDER BY zone_code",
            JID, MUNI)
        print(f"applied {len(rows)} Mount Pleasant (Westchester) row(s):")
        for r in rows:
            print(f"  {r['zone_code']:6} self_storage={r['ss']:11} light_ind={r['li']:11} "
                  f"luxury_garage={r['lgc']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
