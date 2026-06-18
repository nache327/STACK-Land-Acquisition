"""Tredyffrin Township (Chester County PA) — Office/Industrial + Commercial verdicts.

Grounded in Tredyffrin Zoning Ordinance Ch. 208, pasted by Nache. Self-storage is
EXPLICITLY named in the use tables — no convention inference.

§208-40 Table 40.1 (Office & Industrial District Uses), "Self-storage facility" row:
  PIP = P  -> PERMITTED   (also Warehouse=P, manufacturing=P → light_industrial permitted)
  LI  = P  -> PERMITTED   (also Warehouse=P, manufacturing=P → light_industrial permitted)
  O   = SE -> CONDITIONAL (also Warehouse=SE → light_industrial conditional)

§208-61 Table 61.1 (Commercial District Uses): no self-storage / warehouse row at all:
  C-1 = (absent) -> PROHIBITED (silence)
  C-2 = (absent) -> PROHIBITED (silence)

Other bound codes:
  IO  (Art XIII Institutional Overlay, §208-45) — conditional institutional uses only
       (residential care/health/church/schools); self-storage not listed; §208-43 IO does
       NOT overlay LI/PIP. -> PROHIBITED (silence).
  PA  (Art XI Planned Apartment, §208-37) — residential apartment use. -> PROHIBITED (silence).

HELD (use tables not provided): TCD (Town Center §208-69), TD (Transit §208-81).
R1-R4/R1-2/RC already prohibited in _apply_tredyffrin_residential_prohibited.py.

Muni-specific municipality='Tredyffrin Township' (catch #28/#33). asyncpg human-UPSERT
(corrected catch #29 — NOT factory_safe_write). Idempotent.
Run: python scripts/_apply_tredyffrin_office_industrial.py
"""
import asyncio
import json

import asyncpg

JID = "7f5293ff-13e8-4641-a420-49bccb13b407"  # Chester County, PA (Tredyffrin-scoped)
MUNI = "Tredyffrin Township"

# zone -> (self_storage, light_industrial, confidence, cited_subsection)
VERDICTS = {
    "PIP": ("permitted", "permitted", 0.98,
            "§208-40 Table 40.1: 'Self-storage facility' = P (permitted) in PIP; Warehouse = P"),
    "LI":  ("permitted", "permitted", 0.98,
            "§208-40 Table 40.1: 'Self-storage facility' = P (permitted) in LI; Warehouse = P"),
    "O":   ("conditional", "conditional", 0.95,
            "§208-40 Table 40.1: 'Self-storage facility' = SE (special exception) in O → conditional; Warehouse = SE"),
    "C1":  ("prohibited", "unclear", 0.90,
            "§208-61 Table 61.1 (Commercial District Uses): self-storage/warehouse absent from C-1 column; silence rule"),
    "C2":  ("prohibited", "unclear", 0.90,
            "§208-61 Table 61.1 (Commercial District Uses): self-storage/warehouse absent from C-2 column; silence rule"),
    "IO":  ("prohibited", "unclear", 0.85,
            "Art XIII §208-45 Institutional Overlay — conditional institutional uses only; self-storage not listed; §208-43 IO does not overlay LI/PIP; silence rule"),
    "PA":  ("prohibited", "unclear", 0.90,
            "Art XI §208-37 Planned Apartment District — residential apartment use; self-storage not permitted; silence rule"),
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
            cites = json.dumps([{"ordinance": "Tredyffrin Township Zoning Ordinance Ch. 208",
                                 "section": cite.split(":")[0].split("(")[0].strip(),
                                 "basis": f"Self-storage = {ss} in {zc} per {cite}"}])
            note = f"{zc}: self_storage {ss}, light_industrial {li}. {cite}"
            await con.execute(SQL, JID, zc, f"Tredyffrin {zc}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, light_industrial::text li, confidence, "
            "human_reviewed hr FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 "
            "AND zone_code=ANY($3::text[]) AND deleted_at IS NULL ORDER BY zone_code",
            JID, MUNI, list(VERDICTS))
        print(f"applied {len(rows)} muni-specific (Tredyffrin Township) rows:")
        for r in rows:
            print(f"  {r['zone_code']:4} self_storage={r['ss']:11} light_ind={r['li']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
