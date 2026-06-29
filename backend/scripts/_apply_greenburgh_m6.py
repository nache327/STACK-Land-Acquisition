"""Town of Greenburgh (Westchester County, NY) — M-6 self-storage verdict.

Grounded in Town of Greenburgh Code § 285-17 "M-6 Multifamily Residence District" (pasted verbatim).
Despite the "M-" prefix (which elsewhere often denotes industrial), Greenburgh's M-6/M-10/M-14/M-22/
M-25/M-174 are all MULTIFAMILY RESIDENCE districts. M-6 permitted principal uses are limited to:
one-family detached dwellings, multifamily dwellings, public parks/playgrounds, firehouses/police/
public-safety, other municipal buildings, and places of religious worship. Special permit uses:
private/social clubs, nursery schools/day-care. Accessory uses are residential (private garages for
parking, pools, etc.). No warehouse, storage, distribution, or industrial use is listed.

  M-6 -> self_storage / mini_warehouse / light_industrial / luxury_garage_condo = PROHIBITED.

Closes the 560 Taxter Rd "armed-pending" lead (a Land/Residential listing, score 42 — a residential
zone, not a development needle). Muni-specific municipality='Greenburgh' in the Westchester County, NY
jurisdiction. asyncpg human-UPSERT (catch #29). Run: python scripts/_apply_greenburgh_m6.py
"""
import asyncio
import json

import asyncpg

JID = "3e706886-919f-4ecf-b5aa-567040e295e8"  # Westchester County, NY
MUNI = "Greenburgh"
CITE = ("Town of Greenburgh Code § 285-17 M-6 Multifamily Residence District — permitted principal uses "
        "are dwellings/parks/civic/religious only; no storage, warehouse, or industrial use listed")

SQL = """
INSERT INTO zone_use_matrix
 (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
  light_industrial, luxury_garage_condo, citations, cited_subsection, confidence,
  human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$4,'prohibited','prohibited','prohibited','prohibited',$5::jsonb,$6,$7,true,'human',$8,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET self_storage='prohibited', mini_warehouse='prohibited', light_industrial='prohibited',
  luxury_garage_condo='prohibited', citations=EXCLUDED.citations, cited_subsection=EXCLUDED.cited_subsection,
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
        cites = json.dumps([{"ordinance": "Town of Greenburgh Code § 285-17",
                             "section": "M-6 Multifamily Residence District", "basis": CITE}])
        await con.execute(SQL, JID, "M-6", "Greenburgh M-6 Multifamily Residence", MUNI,
                          cites, "§ 285-17 M-6 Multifamily Residence District", 0.92,
                          f"M-6: self_storage prohibited. {CITE}")
        r = await con.fetchrow(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr FROM zone_use_matrix "
            "WHERE jurisdiction_id=$1 AND municipality=$2 AND zone_code='M-6' AND deleted_at IS NULL", JID, MUNI)
        print(f"applied Greenburgh M-6: self_storage={r['ss']} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
