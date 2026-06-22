"""Newtown Township (BUCKS County PA) — self-storage verdicts from the Newtown Area JMZO.

Grounded in the Newtown Area Joint Municipal Zoning Ordinance Table of Use Regulations (pasted).
NT = Newtown Township column. Use G4 "Mini Storage" is the explicit self-storage use:

  LI   (Light Industrial)        — G4 Mini Storage = P, G3 Wholesale/Warehousing = P -> PERMITTED (0.97)
  O-LI (Office-Light Industrial) — G4 Mini Storage = P, G3 Wholesale/Warehousing = P -> PERMITTED (0.97)
  (catch #37: verbatim went the FAVORABLE way — Mini Storage explicitly permitted, not convention.
   O-LI did NOT invert to prohibited as the mixed-code prior suggested.)

  All other NT districts — G4 Mini Storage = N (explicitly not permitted) -> PROHIBITED (0.95):
  CM, OR, CC, PC, TC, TC2, R-1, R-2, PS, PS-2, MS, EIR, POS.

HELD (not in the JMZO column set): BR-2, REC (1 parcel each).

light_industrial=permitted for LI/O-LI (G3 Wholesale/Warehousing=P, G2 Research=P; G1 Manufacturing=CU).
Muni-specific municipality='Newtown Township' in BUCKS jurisdiction (catch #28/#38 — verified Bucks, JMZO
codes match parcels). asyncpg human-UPSERT (catch #29). Run: python scripts/_apply_newtown_bucks.py
"""
import asyncio
import json

import asyncpg

JID = "b5fb97a5-39f5-4aed-8701-494eab075c97"  # Bucks County, PA
MUNI = "Newtown Township"
JMZO = "Newtown Area JMZO Table of Use Regulations (NT column)"

# zone -> (self_storage, light_industrial, confidence, cite)
PERM = (f"{JMZO}: Use G4 Mini Storage = P (permitted); G3 Wholesale/Warehousing = P", 0.97)
VERDICTS = {
    "LI":   ("permitted", "permitted", *PERM),
    "O-LI": ("permitted", "permitted", *PERM),
}
for z in ["CM", "OR", "CC", "PC", "TC", "TC2", "R-1", "R-2", "PS", "PS-2", "MS", "EIR", "POS"]:
    VERDICTS[z] = ("prohibited", "unclear", f"{JMZO}: Use G4 Mini Storage = N (not permitted) in {z}; G3 Wholesale/Warehousing = N", 0.95)

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
        jn = await con.fetchval("SELECT name FROM jurisdictions WHERE id=$1", JID)
        assert jn and "Bucks" in jn, f"jurisdiction check failed: {jn}"
        await con.execute("SET statement_timeout='60s'")
        for zc, (ss, li, cite, conf) in VERDICTS.items():
            cites = json.dumps([{"ordinance": "Newtown Area JMZO", "section": "Table of Use Regulations Use G4 Mini Storage",
                                 "basis": f"self_storage={ss} in {zc} per {cite}"}])
            note = f"{zc}: self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Newtown Twp {zc}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr FROM zone_use_matrix "
            "WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL ORDER BY self_storage, zone_code",
            JID, MUNI)
        print(f"applied {len(rows)} Newtown Township (Bucks) rows:")
        for r in rows:
            print(f"  {r['zone_code']:6} self_storage={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
