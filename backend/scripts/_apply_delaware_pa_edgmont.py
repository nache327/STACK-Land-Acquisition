"""Edgmont Township (Delaware County PA) — Stage-4 self-storage verdicts. eCode360
Ch. 365 Zoning, Articles XI-XVII + XXVIII pasted 2026-07-07.

LI (§ 365-106 + Article XXVIII) — the county's first EXPLICITLY-NAMED conditional
  self-storage: § 365-164B(1) "Public self-storage facilities may be permitted in the
  following zoning district by conditional use: (a) LI, Light Industrial District",
  cross-referenced at § 365-106C(8) "Public self-storage facility in accordance with
  Article XXVIII". Also § 365-106A(4) "Warehouse, wholesale, storage or distribution
  use" BY RIGHT — but the specific controls: self-storage is expressly conditional.
  -> self_storage/mini_warehouse CONDITIONAL (0.95 — named, the strongest conditional
  basis; Art XXVIII sets detailed standards incl. outdoor vehicle/RV/boat storage).
  light_industrial PERMITTED (A(5) light manufacturing by right).
  luxury_garage_condo CONDITIONAL (0.75): Art XXVIII expressly includes "outside
  storage of motor vehicles, recreational vehicles and boats"; plus C(16) catch-all.
  13 pool parcels >=1.5ac.

C-1 (§ 365-72) / C-2 (§ 365-81) / C-3 (§ 365-89) / POC (§ 365-101) / OR (§ 365-116) /
PRD-1..4 (§ 365-52) — closed lists ("...and no other"); no storage use (POC's only
  storage language is ACCESSORY document/records storage § 365-101B(2); OR even
  prohibits hazardous storage) -> PROHIBITED (0.92). Kills C-2 (8) + C-3 (5) pools.

HELD (not pasted): MD (3 pool parcels), R-*.

Muni-specific municipality='Edgmont Township' (catch #33 family); human-UPSERT
(catch #29). Run: python scripts/_apply_delaware_pa_edgmont.py
"""
import asyncio
import json

import asyncpg

JID = "de8945f7-9ad8-4441-a207-83ea372e1f48"  # Delaware County, PA
MUNI = "Edgmont Township"
ORD = "Edgmont Township Code Ch. 365 Zoning (eCode360 https://ecode360.com/34064744)"

_LI_QUOTE = (
    "Public self-storage facilities may be permitted in the following zoning district "
    "by conditional use ... (a) LI, Light Industrial District."
)

# zone -> (ss, mw, li, lgc, conf, section, verbatim_quote, note)
VERDICTS = {
    "LI": ("conditional", "conditional", "permitted", "conditional", 0.95,
           "§ 365-164B(1) + § 365-106C(8)",
           _LI_QUOTE,
           "self-storage EXPLICITLY NAMED as conditional use (Article XXVIII Public "
           "Self-Storage, cross-ref § 365-106C(8)); § 365-106A(4) warehouse by right; "
           "A(5) light manufacturing by right. garage_condo: Art XXVIII includes "
           "'outside storage of motor vehicles, recreational vehicles and boats' -> "
           "conditional."),
}
_CLOSED = "closed list ('...and no other'); no storage use named"
for z, sec, quote, extra in (
    ("C-1", "§ 365-72", "for any one or more of the following uses and for no other", _CLOSED),
    ("C-2", "§ 365-81", "for any one or more of the following uses and for no other", _CLOSED),
    ("C-3", "§ 365-89", "for any of the following uses and no other", _CLOSED),
    ("POC", "§ 365-101", "for any of the following purposes and no other",
     _CLOSED + "; only ACCESSORY 'storage of documents, records and personal property "
     "... in conjunction with a permitted use' § 365-101B(2)"),
    ("OR", "§ 365-116", "for any of the following uses and no other",
     "outdoor recreation district; § 365-116D(4) even prohibits hazardous-materials storage"),
    ("PRD-1", "§ 365-52A", "for any of the following uses and no other", "residential PRD closed list"),
    ("PRD-2", "§ 365-52B", "for any of the following uses and no other", "residential PRD closed list"),
    ("PRD-3", "§ 365-52C", "for any of the following uses and no other", "residential PRD closed list"),
    ("PRD-4", "§ 365-52D", "for any of the following uses and no other", "residential PRD closed list"),
):
    VERDICTS[z] = ("prohibited", "prohibited", "prohibited", "prohibited", 0.92, sec, quote, extra)

SQL = """
INSERT INTO zone_use_matrix
 (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
  light_industrial, luxury_garage_condo, citations, cited_subsection, confidence,
  human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$4,$5::use_permission_enum,$6::use_permission_enum,$7::use_permission_enum,
  $8::use_permission_enum,$9::jsonb,$10,$11,true,'human',$12,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET self_storage=EXCLUDED.self_storage, mini_warehouse=EXCLUDED.mini_warehouse,
  light_industrial=EXCLUDED.light_industrial, luxury_garage_condo=EXCLUDED.luxury_garage_condo,
  citations=EXCLUDED.citations, cited_subsection=EXCLUDED.cited_subsection,
  confidence=EXCLUDED.confidence, human_reviewed=true, classification_source='human',
  notes=EXCLUDED.notes, updated_at=now()
"""


async def main() -> None:
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
    try:
        jn = await con.fetchval("SELECT name FROM jurisdictions WHERE id=$1", JID)
        assert jn == "Delaware County, PA", jn
        await con.execute("SET statement_timeout='60s'")
        for zc, (ss, mw, li, lgc, conf, section, quote, note) in VERDICTS.items():
            cites = json.dumps([{"ordinance": ORD, "section": section, "quote": quote}])
            await con.execute(
                SQL, JID, zc, f"Edgmont Twp {zc}", MUNI, ss, mw, li, lgc,
                cites, section, conf,
                f"{zc}: self_storage {ss} — {section}: \"{quote}\" — {note}",
            )
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence conf, human_reviewed hr, "
            "cited_subsection sec FROM zone_use_matrix WHERE jurisdiction_id=$1 "
            "AND municipality=$2 AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} Edgmont Township rows:")
        for r in rows:
            print(f"  {r['zone_code']:6} ss={r['ss']:11} conf={r['conf']} hr={r['hr']} {r['sec'][:38]}")
    finally:
        await con.close()


asyncio.run(main())
