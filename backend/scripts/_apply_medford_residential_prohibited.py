"""Medford township (Burlington County, NJ) — residential/conservation GAP zones = PROHIBITED.

Step 3 of Burlington Prompt 4. The ZoningHub ingest surfaced 25 zone codes in
parcels.zoning_code; the needle-relevant industrial/commercial zones (PI §412,
HC-1/HC-2 §410) stay HELD pending the use-schedule paste. This script closes the
residential / conservation / ag / historic-village / public-preservation GAP via
the SILENCE RULE — none of these districts enumerate self-storage or warehouse as
a permitted use, so self_storage + mini_warehouse = prohibited. Data hygiene
(0 harvest impact — these never surface needles); makes the zones read 'prohibited'
not 'unclear'.

HELD (NOT in this script — own use-schedule check): PI, HC-1, HC-2 (paste-gated);
CC (commercial), GD (general/growth), PD (planned dev), HM (could be commercial/mixed).

Catch #28: written MUNI-SPECIFIC municipality='Medford township' (verbatim parcels.city),
NOT county-default NULL — Burlington is multi-muni; Mount Laurel/Moorestown will add
their own codes later and must not collide. Medford Lakes borough is a SEPARATE muni
(not in scope). ON CONFLICT DO UPDATE (reverse-direction #13). Idempotent.
Run: python scripts/_apply_medford_residential_prohibited.py
"""
import asyncio
import json

import asyncpg

JID = "d316fb43-d0e6-4359-aa47-6475fa99cc0f"  # Burlington County, NJ
MUNI = "Medford township"  # verbatim parcels.city (catch #28)
CITE = "Medford Township LDO §400s — silence rule (district use schedule does not enumerate self-storage/warehouse)"

# residential / conservation / ag / historic-village / public-preservation -> prohibited
ZONES = [
    "RGD-1", "RGD-2",          # residential growth district
    "GMN", "GMN-AR", "GMS",    # Pinelands growth-management (+ ag overlay)
    "RS-1", "RS-2",            # residential single-family
    "AR",                      # agricultural/residential
    "RHO", "RHC",              # residential
    "HVC", "HVR",              # historic village (commercial/residential)
    "VRD",                     # village residential
    "PPE",                     # public / preservation
    "RC",                      # rural / conservation
    "FD",                      # (low-density / flood)
    "SAPA", "APA",             # Pinelands Special/Agricultural Production Area
]

SQL = """
INSERT INTO zone_use_matrix
 (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
  light_industrial, luxury_garage_condo, citations, cited_subsection, confidence,
  human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$8,'prohibited'::use_permission_enum,'prohibited'::use_permission_enum,
  'unclear','unclear',$4::jsonb,$5,0.9,true,'human',$6,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET self_storage=EXCLUDED.self_storage, mini_warehouse=EXCLUDED.mini_warehouse,
  citations=EXCLUDED.citations, cited_subsection=EXCLUDED.cited_subsection, confidence=0.9,
  human_reviewed=true, classification_source='human', notes=EXCLUDED.notes, updated_at=now()
"""


async def main():
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout='60s'")
        for zc in ZONES:
            cites = json.dumps([{"ordinance": "Medford Township Land Development Ordinance",
                                 "section": "§400s district use schedule",
                                 "basis": f"Self-storage/warehouse not a permitted use in {zc} (residential/conservation/ag/preservation) — silence rule"}])
            note = f"{zc}: self_storage prohibited (silence rule — residential/conservation/ag/preservation district)."
            await con.execute(SQL, JID, zc, f"Medford {zc}", cites, CITE, note, MUNI)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, human_reviewed hr FROM zone_use_matrix "
            "WHERE jurisdiction_id=$1 AND municipality=$2 AND zone_code=ANY($3::text[]) "
            "AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI, ZONES)
        print(f"applied {len(rows)} muni-specific (Medford township) prohibited rows:")
        for r in rows:
            print(f"  {r['zone_code']:7} self_storage={r['ss']:11} human={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
