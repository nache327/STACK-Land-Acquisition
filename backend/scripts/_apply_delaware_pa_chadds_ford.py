"""Chadds Ford Township (Delaware County PA) — Stage-4 self-storage verdicts. eCode360
Ch. 135 Zoning, Articles VIII-XIV + XVII pasted 2026-07-07 (CC truncated in accessory
subsection — principal/conditional use lists complete).

LI (§ 135-88/89) — closed list; NO general warehouse-by-right (§ 135-88J is
  "Wholesaling and distributing activities WHEN ASSOCIATED WITH PERMITTED USES" — a
  tied-use clause, not general warehousing; warehouse=>conditional convention does NOT
  fire). Self-storage named NOWHERE township-wide in the pasted articles. BUT
  § 135-89A(2) conditional: "Any other use required by law to be permitted and not
  specifically permitted in any other zoning district" — the classic PA curative
  catch-all (MPC de jure exclusion doctrine): the lawful-but-unlisted self-storage use
  has a genuine conditional pathway here, in the district it best fits.
  -> self_storage/mini_warehouse CONDITIONAL (0.75 — catch-all basis, honestly lower
  confidence than a named use). light_industrial PERMITTED (0.95, district core).
  luxury_garage_condo conditional (0.70, same catch-all). 12 pool parcels >=1.5ac.

LI-1 (§ 135-96/97) — LI by reference ("Any uses that are permitted by right ... in LI"
  + "Any uses permitted by conditional use in LI") -> same verdicts as LI.

B (§ 135-55) / B-1 (§ 135-61, B by reference + vehicles/vape/dispensary) /
PBC (§ 135-69) / PBC-1 (§ 135-75, PBC by reference + vehicles) / POC (§ 135-82) —
  closed lists ("...and for no other"); no storage use -> PROHIBITED (0.92).
CC (§ 135-113) — cultural campus; uses-by-right + conditional lists complete in paste
  (accessory subsection truncated — accessory can't create a principal use); no storage;
  B(6) even prohibits outdoor storage for its small retail -> PROHIBITED (0.90).

HELD (not pasted): MC, R-1/R-2/R-MA.

Muni-specific municipality='Chadds Ford Township' (catch #33 family); human-UPSERT
(catch #29). Run: python scripts/_apply_delaware_pa_chadds_ford.py
"""
import asyncio
import json

import asyncpg

JID = "de8945f7-9ad8-4441-a207-83ea372e1f48"  # Delaware County, PA
MUNI = "Chadds Ford Township"
ORD = "Chadds Ford Township Code Ch. 135 Zoning (eCode360 https://ecode360.com/13219528)"

_LI_QUOTE = (
    "Any other use required by law to be permitted and not specifically permitted in "
    "any other zoning district."
)
_LI_NOTE = (
    "self-storage named NOWHERE township-wide; no general warehouse-by-right "
    "(§ 135-88J wholesaling/distributing is tied to permitted uses — convention does "
    "not fire). Conditional via the § 135-89A(2) PA curative catch-all (MPC de jure "
    "exclusion doctrine) — honest lower confidence; upgrade only on a Board precedent."
)

# zone -> (ss, mw, li, lgc, conf, section, verbatim_quote, note)
VERDICTS = {
    "LI": ("conditional", "conditional", "permitted", "conditional", 0.75,
           "§ 135-89A(2)", _LI_QUOTE, _LI_NOTE),
    "LI-1": ("conditional", "conditional", "permitted", "conditional", 0.75,
             "§ 135-96A + § 135-97A (LI by reference)",
             "Any uses that are permitted by right as a Principal Permitted Uses in LI "
             "Light Industrial District. / Any uses permitted by conditional use in LI "
             "Light Industrial District.",
             "LI verdicts inherited by reference; adds correctional + marijuana "
             "grower/processor conditionals only. " + _LI_NOTE),
}
for z, sec, quote, extra in (
    ("B", "§ 135-55", "for any of the following uses and for no other",
     "retail/office/service closed list; no storage use"),
    ("B-1", "§ 135-61", "for any of the following uses and for no other",
     "B by reference + motor-vehicle/vape/dispensary conditionals; no storage use"),
    ("PBC", "§ 135-69", "for any of the following uses and for no other",
     "planned business center closed list; no storage use"),
    ("PBC-1", "§ 135-75", "for any of the following uses and for no other",
     "PBC by reference + motor-vehicle conditionals; no storage use"),
    ("POC", "§ 135-82", "for any of the following uses and for no other",
     "offices + recreation only; no storage use"),
    ("CC", "§ 135-113", "for any of the following purposes or combinations thereof, and no other",
     "cultural campus; B(6) small retail expressly prohibits outdoor storage; no storage use"),
):
    conf = 0.90 if z == "CC" else 0.92
    VERDICTS[z] = ("prohibited", "prohibited", "prohibited", "prohibited", conf, sec, quote, extra)

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
                SQL, JID, zc, f"Chadds Ford Twp {zc}", MUNI, ss, mw, li, lgc,
                cites, section, conf,
                f"{zc}: self_storage {ss} — {section}: \"{quote}\" — {note}",
            )
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence conf, human_reviewed hr, "
            "cited_subsection sec FROM zone_use_matrix WHERE jurisdiction_id=$1 "
            "AND municipality=$2 AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} Chadds Ford Township rows:")
        for r in rows:
            print(f"  {r['zone_code']:6} ss={r['ss']:11} conf={r['conf']} hr={r['hr']} {r['sec'][:42]}")
    finally:
        await con.close()


asyncio.run(main())
