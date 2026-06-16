"""Medford township (Burlington County, NJ) — PI / HC-1 / HC-2 / HM verdicts.

Grounded in Medford Township LDO §412 (PI) + §410 (HC-1/HC-2/HM), pasted by Nache.

  PI  (Planned Industrial)  -> self_storage CONDITIONAL
      §412.A permits BY-RIGHT: #1 Limited Manufacturing (incl. processing/storage/
      servicing), #2 Wholesaling & Distributing, #5 Warehousing (explicit),
      #7 Building Materials Storage Yards & Lumberyards. Self-storage / mini-warehouse
      NOT named. Warehouse-by-right + self-storage-unnamed -> CONDITIONAL
      (Cresskill P&L convention; strongest convention case to date — 4 warehouse-
      adjacent uses explicit). The needle zone.

  HC-1 (Highway Commercial-1) -> PROHIBITED (silence rule)
      §410.A permits motels/hotels/auto sales/fire stations/printing/telephone/
      public garages (storage capped 48h)/service stations/retail/recreational/
      fast food/shopping centers/car washes. No warehouse/storage/self-storage.

  HC-2 (Highway Commercial-2) -> PROHIBITED (silence rule)
      §410.A as HC-1 + §406.A AR Agricultural Retention inheritance. No warehouse/storage.

  HM  (Highway Management) -> PROHIBITED (silence rule)
      §410B — HC-character + CCRC/age-restricted/assisted-living. No warehouse/storage.

self_storage + mini_warehouse set per the schedule; light_industrial /
luxury_garage_condo left 'unclear' (spec named only self-storage — no fabrication).

NOTE ON MECHANISM (catch #29 corrected): written via the hand-verdict asyncpg
human-UPSERT — NOT factory_safe_write(). factory_safe_write hardcodes
human_reviewed=false, coerces classification_source to op5_factory*, and does
ON CONFLICT DO NOTHING; it is the FACTORY chokepoint that PROTECTS human rows,
it cannot PRODUCE one. Routing a human verdict through it would land
human_reviewed=false -> invisible to the SN digest storageVerdictMode='only'
gate (which requires human_reviewed=TRUE) -> the harvest would never see it.

Catch #28: muni-specific municipality='Medford township' (verbatim parcels.city).
ON CONFLICT DO UPDATE (reverse-direction #13). Idempotent.
Run: python scripts/_apply_medford_pi_hc.py
"""
import asyncio
import json

import asyncpg

JID = "d316fb43-d0e6-4359-aa47-6475fa99cc0f"  # Burlington County, NJ
MUNI = "Medford township"

# zone_code -> (self_storage verdict, confidence, cited_subsection)
VERDICTS = {
    "PI": ("conditional", 0.95,
           "§412.A (Permitted Uses 1,2,5,7 — Limited Manufacturing incl. storage, "
           "Wholesaling & Distributing, Warehousing, Building Materials Storage Yards "
           "all by-right; self-storage unnamed; convention fires conditional — Cresskill precedent)"),
    "HC-1": ("prohibited", 0.92,
             "§410.A (motels/hotels/auto sales/fire stations/printing/telephone/public garages "
             "[48h storage cap]/service stations/retail/recreational/fast food/shopping centers/"
             "car washes; no warehouse/storage/self-storage; silence rule)"),
    "HC-2": ("prohibited", 0.92,
             "§410.A (as HC-1 + §406.A AR Agricultural Retention inheritance; "
             "no warehouse/storage/self-storage; silence rule)"),
    "HM": ("prohibited", 0.90,
           "§410B (Highway Management — HC-character + CCRC/age-restricted/assisted-living; "
           "no warehouse/storage/self-storage; silence rule)"),
}

SQL = """
INSERT INTO zone_use_matrix
 (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
  light_industrial, luxury_garage_condo, citations, cited_subsection, confidence,
  human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$7,$4::use_permission_enum,$4::use_permission_enum,
  'unclear','unclear',$5::jsonb,$6,$8,true,'human',$9,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET self_storage=EXCLUDED.self_storage, mini_warehouse=EXCLUDED.mini_warehouse,
  citations=EXCLUDED.citations, cited_subsection=EXCLUDED.cited_subsection,
  confidence=EXCLUDED.confidence, human_reviewed=true, classification_source='human',
  notes=EXCLUDED.notes, updated_at=now()
"""


async def main():
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout='60s'")
        for zc, (verdict, conf, cite) in VERDICTS.items():
            cites = json.dumps([{"ordinance": "Medford Township Land Development Ordinance",
                                 "section": cite.split(" ", 1)[0],
                                 "basis": f"Self-storage = {verdict} in {zc} per {cite}"}])
            note = f"{zc}: self_storage {verdict} ({cite})."
            await con.execute(SQL, JID, zc, f"Medford {zc}", verdict, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr, "
            "classification_source src FROM zone_use_matrix "
            "WHERE jurisdiction_id=$1 AND municipality=$2 AND zone_code=ANY($3::text[]) "
            "AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI, list(VERDICTS))
        print(f"applied {len(rows)} muni-specific (Medford township) rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} self_storage={r['ss']:11} conf={r['confidence']} "
                  f"human={r['hr']} src={r['src']}")
    finally:
        await con.close()


asyncio.run(main())
