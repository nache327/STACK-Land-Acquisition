"""Raritan I-2 (Hunterdon, IMMEDIATE) + Mount Laurel / Moorestown (Burlington, PRE-STAGE) verdicts.

Grounded in Nache's ordinance pastes. Hand verdicts via asyncpg human-UPSERT (corrected catch #29 —
NOT factory_safe_write, which can't write human rows). Muni-specific (catch #21 Raritan≠Flemington / #28).

IMMEDIATE (Hunterdon parcels already zoned — binds + harvests now):
  Raritan township I-2  -> CONDITIONAL  (§296-123.B(2) warehousing/wholesale/distribution by-right +
      B(3) trucking terminals; self-storage unnamed; Cresskill convention). conf 0.95.
      NOTE: an existing county-default (municipality=NULL) I-2='permitted' human_reviewed=FALSE heuristic
      row stays untouched; this muni-specific row is a NEW key the scoring join prefers for Raritan.

PRE-STAGE (Burlington — Mount Laurel/Moorestown parcels NOT zoned yet; rows are inert until shapefiles
land and parcels.zoning_code + city bind. catch #27. At ingest, reconcile that the shapefile's zone-code
strings + parcels.city match what's written here):
  Mount Laurel township  I    -> CONDITIONAL  (§154-56.A purpose "...storing and wholesaling" +
      C(13) Motor vehicle storage explicit + C(18) impound conditional; self-storage unnamed; convention). 0.85.
      [SRI (§154-63) HELD per Nache — Specially Restricted Industrial, own use list.]
  Moorestown township   BP-1  -> PERMITTED   (§180-67.2.A(12) "Facilities that provide storage, including
      self and personal storage" — EXPLICIT principal use; no inference). 0.98. Headline wealth-tail verdict.
  Moorestown township   BP-2  -> PROHIBITED  (§180-69.A tech/mfg/aerospace/IT/sci/edu only; B(5) warehousing
      accessory-only; D(1) "all uses not expressly permitted"; self-storage unnamed; silence). 0.92.
  Moorestown township   SRC   -> PROHIBITED  (self-storage not in permitted/conditional/accessory lists;
      silence rule, per Nache ordinance review — no verbatim cite to Claude Code). 0.85.
  Moorestown township   LTC   -> PROHIBITED  (same — silence rule per Nache review). 0.85.

self_storage + mini_warehouse set per verdict; light_industrial / luxury_garage_condo left 'unclear'
(spec named only self-storage — no fabrication, incl. BP-1's TK/garage-condo which isn't explicitly cited).
Run: python scripts/_apply_raritan_ml_moorestown.py
"""
import asyncio
import json

import asyncpg

HUNTERDON = "e8612f49-218b-48cc-9eb0-a1dd90cf583d"
BURLINGTON = "d316fb43-d0e6-4359-aa47-6475fa99cc0f"

# (jid, municipality, zone_code, zone_name, verdict, confidence, cited_subsection)
ROWS = [
    (HUNTERDON, "Raritan township", "I-2", "Raritan I-2 Major Industrial", "conditional", 0.95,
     "§296-123.B(2) Warehousing, wholesale and distribution facilities permitted by-right + "
     "§296-123.B(3) Trucking terminals; self-storage unnamed; Cresskill P&L convention fires -> conditional"),
    (BURLINGTON, "Mount Laurel township", "I", "Mount Laurel Industrial (Art VIII)", "conditional", 0.85,
     "§154-56.A purpose \"...manufacturing, processing, fabricating, repairing, storing and wholesaling\" + "
     "§154-56.C(13) Motor vehicle storage explicit + C(18) impound conditional; self-storage unnamed; convention -> conditional"),
    (BURLINGTON, "Moorestown township", "BP-1", "Moorestown Business Park 1", "permitted", 0.98,
     "§180-67.2.A(12): \"Facilities that provide storage, including self and personal storage\" — explicit principal permitted use"),
    (BURLINGTON, "Moorestown township", "BP-2", "Moorestown Business Park 2", "prohibited", 0.92,
     "§180-69.A principal uses tech/manufacturing/aerospace/IT/scientific/educational only; §180-69.B(5) warehousing accessory-only; "
     "§180-69.D(1) \"all uses not expressly permitted\" silence rule; self-storage unnamed -> prohibited"),
    (BURLINGTON, "Moorestown township", "SRC", "Moorestown Specially Restricted Commercial", "prohibited", 0.85,
     "Moorestown LDO SRC: self-storage not named in permitted/conditional/accessory use lists; silence rule (per Nache ordinance review)"),
    (BURLINGTON, "Moorestown township", "LTC", "Moorestown Lenola Town Center", "prohibited", 0.85,
     "Moorestown LDO LTC: self-storage not named in permitted/conditional/accessory use lists; silence rule (per Nache ordinance review)"),
]

SQL = """
INSERT INTO zone_use_matrix
 (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
  light_industrial, luxury_garage_condo, citations, cited_subsection, confidence,
  human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$4,$5::use_permission_enum,$5::use_permission_enum,
  'unclear','unclear',$6::jsonb,$7,$8,true,'human',$9,now(),now())
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
        for jid, muni, zc, zname, verdict, conf, cite in ROWS:
            cites = json.dumps([{"ordinance": f"{muni} LDO", "section": cite.split(";")[0],
                                 "basis": f"Self-storage = {verdict} in {zc} per {cite}"}])
            note = f"{zc} ({muni}): self_storage {verdict}. {cite}"
            await con.execute(SQL, jid, zc, zname, muni, verdict, cites, cite, conf, note)
        # verify
        rows = await con.fetch(
            """SELECT j.name jur, m.municipality, m.zone_code, m.self_storage::text ss, m.confidence,
                 m.human_reviewed hr, m.classification_source src
               FROM zone_use_matrix m JOIN jurisdictions j ON j.id=m.jurisdiction_id
               WHERE (m.jurisdiction_id=$1 AND m.municipality='Raritan township' AND m.zone_code='I-2')
                  OR (m.jurisdiction_id=$2 AND m.municipality IN ('Mount Laurel township','Moorestown township'))
               AND m.deleted_at IS NULL ORDER BY j.name, m.municipality, m.zone_code""",
            HUNTERDON, BURLINGTON)
        print(f"applied {len(rows)} muni-specific verdict rows:")
        for r in rows:
            print(f"  {r['jur'][:13]:13} {r['municipality']:22} {r['zone_code']:5} "
                  f"{r['ss']:11} conf={r['confidence']} hr={r['hr']} src={r['src']}")
    finally:
        await con.close()


asyncio.run(main())
