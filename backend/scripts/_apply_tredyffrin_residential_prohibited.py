"""Tredyffrin Township (Chester County, PA) — residential/conservation zones = PROHIBITED.

Step 4 of the Tredyffrin onboard. Bind-test PASSED (100%, 9,876/9,880 zoned). Closes the
clearly-residential / rural-conservation GAP via the SILENCE RULE — these districts don't
enumerate self-storage/warehouse, so self_storage + mini_warehouse = prohibited. Data hygiene
(0 harvest impact).

HELD (own use-schedule check, NOT in this script):
  - Needle-candidate industrial/office: PIP (14), LI (36), O (61), IO (2) — paste-gated (§use schedules).
  - Commercial/mixed/ambiguous: C1 (220), C2 (95), TCD (362 Town Center), TD (2), PA (646) — verify.

Catch #28/#33: muni-specific municipality='Tredyffrin Township' (verbatim parcels.city from
city_override). ON CONFLICT DO UPDATE (corrected catch #29 — hand verdicts via asyncpg human-UPSERT,
NOT factory_safe_write). Idempotent.
Run: python scripts/_apply_tredyffrin_residential_prohibited.py
"""
import asyncio
import json

import asyncpg

JID = "7f5293ff-13e8-4641-a420-49bccb13b407"  # Chester County, PA (Tredyffrin-scoped)
MUNI = "Tredyffrin Township"
CITE = "Tredyffrin Township Zoning Ordinance — silence rule (residential/conservation district use schedule does not enumerate self-storage/warehouse)"

ZONES = ["R1", "R2", "R3", "R4", "R1/2", "RC"]  # residential + rural-conservation

SQL = """
INSERT INTO zone_use_matrix
 (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
  light_industrial, luxury_garage_condo, citations, cited_subsection, confidence,
  human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$7,'prohibited'::use_permission_enum,'prohibited'::use_permission_enum,
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
            cites = json.dumps([{"ordinance": "Tredyffrin Township Zoning Ordinance",
                                 "section": "district use schedule",
                                 "basis": f"Self-storage/warehouse not a permitted use in {zc} (residential/conservation) — silence rule"}])
            note = f"{zc}: self_storage prohibited (silence rule — residential/conservation district)."
            await con.execute(SQL, JID, zc, f"Tredyffrin {zc}", cites, CITE, note, MUNI)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, human_reviewed hr FROM zone_use_matrix "
            "WHERE jurisdiction_id=$1 AND municipality=$2 AND zone_code=ANY($3::text[]) "
            "AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI, ZONES)
        print(f"applied {len(rows)} muni-specific (Tredyffrin Township) prohibited rows:")
        for r in rows:
            print(f"  {r['zone_code']:6} self_storage={r['ss']:11} human={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
